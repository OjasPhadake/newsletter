#!/usr/bin/env python3
"""norepeat — stop a recurring job from repeating itself.

Anything that runs every day and produces content has the same failure: it
starts saying the same things. A newsletter re-runs a story under a different
link, a standup digest re-reports last week's news, a social bot rediscovers
its own best post. Remembering exact strings is not enough, because the second
telling is never worded the same way.

So this remembers values by *kind*, each with its own cooldown, and matches
them loosely: two lines count as the same if most of the shorter one's content
words appear in the other, or if they share two unusual words. That catches
"Chili's opened a fake loan office next door to a McDonald's" against
"Chili's opened a fake payday-loan shop next door to a McDonald's", and
"Saturn has grown a decagon" against "A ten-sided storm at Saturn's pole".

    from norepeat import Guard

    g = Guard("state.json",
              cooldowns={"story": None, "source": 30},  # None means forever
              fuzzy={"story"})

    for c in g.check({"story": [headline], "source": [domain]}):
        print(c.kind, c.value, c.why)      # empty list means nothing repeats
    g.record({"date": "2026-09-08", "story": [headline], "source": [domain]})

Standalone:

    python3 norepeat.py check  --state s.json --kind story --value "..." --fuzzy
    python3 norepeat.py record --state s.json --kind story --value "..."
    python3 norepeat.py list   --state s.json --kind story

MIT licensed. Single file, standard library only.
"""
import argparse
import json
import os
import re
import sys
from collections import namedtuple
from datetime import date, datetime, timedelta

__version__ = "1.0.0"
__all__ = ["Guard", "Collision", "norm", "norm_name", "toks", "near", "names"]

Collision = namedtuple("Collision", "kind value why")

# Dropped before comparing: too common to carry meaning.
STOP = set("""
a an the and or but if so as at by for from in into of off on to up with within
without over under after before while since until because that this these those
its it his her their our your my is are was were be been being has have had do
does did will would can could should may might must not no nor than then there
here when what which who whom whose how why about again more most other some
such only own same very just now new one two three four five six seven eight
nine ten first second last next per via out down
""".split())

# Long words too common in most feeds to prove anything on their own.
COMMON_LONG = set("""
company companies business businesses billion million trillion percent country
government customers customer announced released research researchers language
languages models modelling learning industry industries technology january
february march april may june july august september october november december
""".split())

NAME_RUN = re.compile(r"[A-Z][\w'’&.\-]*(?:[ \-](?:[A-Z][\w'’&.\-]*|\d+))*")
SENT_START = re.compile(r"[.!?…]\s+")

# Capitalised words that open sentences or name places, platforms and awards.
NOT_A_NAME = set("""
the a an it its this that these those in on at for to of and but or if so as by
with from into through over under after before while since until because when
what which who how why now then most every each no not you your we they there
here both nobody somebody everyone one two three four five six seven eight nine
ten first second third last next is was are were has have had will would can
could should may might must do does did new news read more still just about
january february march april may june july august september october november
december monday tuesday wednesday thursday friday saturday sunday
""".split())


def norm(s):
    """Loose key: lowercase, alphanumerics and single spaces only."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def norm_name(s):
    """Like `norm`, minus the possessive: Chili's and McDonald's lose the s."""
    return re.sub(r"\s+", " ", re.sub(r"\bs\b", "", norm(s))).strip()


def toks(s, stop=STOP):
    """Content words, for loose comparison."""
    return {t for t in norm(s).split() if len(t) > 2 and t not in stop}


def distinctive(t, common=COMMON_LONG):
    return len(t) >= 5 and t not in common


def near(a, b, containment=0.5, min_shared=3, min_distinctive=2):
    """Are two lines the same thing wearing different words?

    Either most of the shorter line's content words also appear in the other,
    or the two share enough unusual words that the overlap cannot be chance.
    Both need `min_shared` words in common first, which is what keeps two
    unrelated headlines about the same industry from colliding.
    """
    if not a or not b:
        return False
    shared = a & b
    if len(shared) < min_shared:
        return False
    if len(shared) / min(len(a), len(b)) >= containment:
        return True
    return sum(1 for t in shared if distinctive(t)) >= min_distinctive


def names(text, first_only=False, ignore=NOT_A_NAME):
    """Proper nouns in a blob of prose — brands, products, people.

    Deliberately crude: capitalised runs, minus the words that open sentences
    or name a month. `first_only` takes just the leading one, which in a
    sentence-case headline is reliably the subject ("Burger King photographed
    marathon finishers"). Good enough to notice a name you used last week; not
    a substitute for real entity recognition.
    """
    text = text or ""
    starts = {0} | {m.end() for m in SENT_START.finditer(text)}
    out = []
    for m in NAME_RUN.finditer(text):
        words = [w.strip(".,;:!?'’\"") for w in m.group(0).split()]
        while words and words[0].lower() in ignore:
            words.pop(0)
        while words and words[-1].lower() in ignore:
            words.pop()
        words = [w for w in words if w]
        if not words:
            continue
        name = " ".join(words)
        n = norm_name(name)
        if not re.search(r"[a-z]", n):
            continue
        if len(n) < 3 and not name.isupper():   # keep HP and KFC, drop initials
            continue
        # A lone capitalised word opening a sentence is usually just the
        # sentence opening. A headline's opening word is its subject.
        if not first_only and len(words) == 1 and m.start() in starts:
            continue
        out.append(name)
        if first_only:
            break
    return out


def dedupe(values, key=norm):
    seen, out = set(), []
    for v in values:
        k = key(v)
        if k and k not in seen:
            seen.add(k)
            out.append(v)
    return out


class Guard:
    """Remembers what a recurring job has already used.

    cooldowns   {kind: days}; None means "never reuse this, ever".
    fuzzy       kinds matched loosely as well as exactly.
    not_checked kinds recorded but never rejected in their own right —
                useful for a weaker signal that should still block a
                stronger kind (see `also_check`).
    also_check  {kind: [other kinds]}; a value of `kind` also collides
                against everything recorded under the listed kinds.
    key_norm    {kind: callable}; per-kind key function, default `norm`.
    """

    def __init__(self, path, cooldowns, fuzzy=(), not_checked=(),
                 also_check=None, key_norm=None, date_field="date",
                 entries_field="entries"):
        self.path = path
        self.entries_field = entries_field
        self.cooldowns = dict(cooldowns)
        self.fuzzy = set(fuzzy)
        self.not_checked = set(not_checked)
        self.also_check = dict(also_check or {})
        self.key_norm = dict(key_norm or {})
        self.date_field = date_field
        self._state = None

    # ---------------------------------------------------------------- state --
    def load(self, force=False):
        if self._state is not None and not force:
            return self._state
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self._state = json.load(f)
        else:
            self._state = {self.entries_field: []}
        self._state.setdefault(self.entries_field, [])
        return self._state

    def save(self, state=None):
        state = state or self.load()
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        self._state = state

    def key(self, kind):
        return self.key_norm.get(kind, norm)

    # ----------------------------------------------------------- inspection --
    def entries(self, kind, within_days=None):
        """{key: (original value, date)} for one kind, within a window."""
        cutoff = (date.today() - timedelta(days=within_days)
                  if within_days is not None else None)
        keyfn = self.key(kind)
        out = {}
        for ed in self.load().get(self.entries_field, []):
            when = ed.get(self.date_field)
            if cutoff:
                try:
                    if datetime.strptime(when, "%Y-%m-%d").date() < cutoff:
                        continue
                except (TypeError, ValueError):
                    continue
            for v in ed.get(kind) or []:
                out.setdefault(keyfn(v), (v, when))
        return out

    def pool(self, kind):
        """Everything `kind` is checked against, its own history plus any
        weaker kinds listed in `also_check`."""
        used = {}
        for other in self.also_check.get(kind, []):
            used.update(self.entries(other, self.cooldowns.get(other)))
        used.update(self.entries(kind, self.cooldowns.get(kind)))
        return used

    # ---------------------------------------------------------------- check --
    def check(self, new, within_batch=True):
        """Collisions between `new` ({kind: [values]}) and everything on record.

        Loose matching runs against history only. Within a single batch it
        stays exact, because two fields of one item legitimately overlap —
        an explainer that unpacks the paper next to it, say.
        """
        found = []
        for kind, values in new.items():
            if kind in self.not_checked or kind not in self.cooldowns:
                continue
            used = self.pool(kind)
            keyfn = self.key(kind)
            loose = ([(toks(v), v, when) for v, when in used.values()]
                     if kind in self.fuzzy else [])
            seen = set()
            for v in values:
                k = keyfn(v)
                if k in used:
                    found.append(Collision(kind, v, f"already used on {used[k][1]}"))
                    continue
                hit = None
                if kind in self.fuzzy:
                    mine = toks(v)
                    for other, oval, when in loose:
                        if near(mine, other):
                            hit = (oval, when)
                            break
                if hit:
                    found.append(Collision(
                        kind, v, f"same as {hit[1]}: {str(hit[0])[:70]!r}"))
                elif within_batch and k in seen:
                    found.append(Collision(kind, v, "duplicated within this batch"))
                else:
                    seen.add(k)
        return found

    # --------------------------------------------------------------- record --
    def record(self, entry, replace_on=()):
        """Append an entry, replacing any existing one matching `replace_on`."""
        state = self.load()
        rows = state[self.entries_field]
        if replace_on:
            sig = tuple(entry.get(f) for f in replace_on)
            rows = [e for e in rows
                    if tuple(e.get(f) for f in replace_on) != sig]
        rows.append(entry)
        rows.sort(key=lambda e: str(e.get(self.date_field, "")))
        state[self.entries_field] = rows
        self.save(state)
        return state


# ------------------------------------------------------------------- CLI ----

def _guard(args):
    return Guard(args.state,
                 cooldowns={args.kind: args.days},
                 fuzzy={args.kind} if getattr(args, "fuzzy", False) else set(),
                 date_field="date")


def main():
    p = argparse.ArgumentParser(description="Stop a recurring job repeating itself.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "record", "list"):
        s = sub.add_parser(name)
        s.add_argument("--state", required=True, help="JSON file holding memory")
        s.add_argument("--kind", required=True, help="what sort of value this is")
        s.add_argument("--days", type=int, default=None,
                       help="cooldown in days (default: forever)")
        if name != "list":
            s.add_argument("--value", nargs="+", required=(name == "record"),
                           default=[], help="one or more values")
        if name == "check":
            s.add_argument("--fuzzy", action="store_true",
                           help="also catch reworded repeats")
        s.set_defaults(cmd=name)
    args = p.parse_args()
    g = _guard(args)

    if args.cmd == "list":
        got = g.entries(args.kind, args.days)
        for _, (val, when) in sorted(got.items(), key=lambda kv: str(kv[1][1])):
            print(f"{when}\t{val}")
        print(f"-- {len(got)} on record", file=sys.stderr)
        return 0

    if args.cmd == "check":
        hits = g.check({args.kind: args.value})
        for c in hits:
            print(f"[{c.kind}] {c.value}\n    {c.why}", file=sys.stderr)
        if hits:
            print(f"FAIL — {len(hits)} collision(s)", file=sys.stderr)
            return 1
        print("OK — nothing repeats.")
        return 0

    g.record({"date": date.today().isoformat(), args.kind: args.value})
    print(f"recorded {len(args.value)} value(s) under {args.kind!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
