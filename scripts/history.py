#!/usr/bin/env python3
"""Duplicate guard for The Morning.

Nothing in this newsletter should ever repeat: not a quote, not an idea, not a
prompt, not a story. Relying on the agent to remember that across months of
issues is not a plan, so it is enforced here instead. `check` exits non-zero
and names every collision; the daily run is not allowed to send until it passes.

    python3 scripts/history.py show
    python3 scripts/history.py check editions/2026-09-04.json
    python3 scripts/history.py record editions/2026-09-04.json
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(HERE, "state", "history.json")

# How long each kind of thing stays "used". None means forever.
COOLDOWN_DAYS = {
    "quote_text":   None,   # a quote is never repeated, full stop
    "quote_author": 90,
    "idea_text":    None,   # nor is an idea
    "idea_prompt":  120,
    "hn_id":        None,
    "link":         45,
}


def norm(s):
    """Loose match, so a reworded repeat is still caught."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def load():
    if not os.path.exists(HISTORY):
        return {"editions": []}
    with open(HISTORY, encoding="utf-8") as f:
        return json.load(f)


def entries(hist, kind, within_days=None):
    """Every recorded value of `kind`, optionally limited to a recent window."""
    cutoff = None
    if within_days is not None:
        cutoff = date.today() - timedelta(days=within_days)
    out = {}
    for ed in hist.get("editions", []):
        try:
            when = datetime.strptime(ed["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if cutoff and when < cutoff:
            continue
        for v in ed.get(kind, []) or []:
            out.setdefault(norm(v), (v, ed["date"]))
    return out


def harvest(ed):
    """Pull the uniqueness-relevant fields out of an edition JSON."""
    q = ed.get("quote") or {}
    ideas = ed.get("ideas") or {}
    items = ideas.get("items") or []

    def idea_text(it):
        return it if isinstance(it, str) else it.get("text")

    links = []
    for s in ed.get("hn") or []:
        links.append(s.get("url"))
    for key in ("trends", "wild", "research"):
        for it in ed.get(key) or []:
            links.append(it.get("url"))
    for st in (ed.get("markets") or {}).get("stories") or []:
        links.append(st.get("url"))

    return {
        "quote_text":   [q.get("text")] if q.get("text") else [],
        "quote_author": [q.get("author")] if q.get("author") else [],
        "idea_text":    [idea_text(i) for i in items if idea_text(i)],
        "idea_prompt":  [ideas["prompt"]] if ideas.get("prompt") else [],
        "hn_id":        [re.sub(r".*id=", "", s.get("hn_url", ""))
                         for s in ed.get("hn") or [] if s.get("hn_url")],
        "link":         [u for u in links if u],
    }


def cmd_show(_):
    hist = load()
    eds = hist.get("editions", [])
    print(f"{len(eds)} edition(s) recorded")
    for kind, days in COOLDOWN_DAYS.items():
        used = entries(hist, kind, days)
        window = "ever" if days is None else f"last {days}d"
        print(f"\n{kind} ({window}) — {len(used)}")
        for _, (val, when) in sorted(used.items(), key=lambda kv: kv[1][1], reverse=True)[:12]:
            print(f"  {when}  {str(val)[:90]}")
    return 0


def cmd_check(args):
    hist = load()
    with open(args.edition, encoding="utf-8") as f:
        new = harvest(json.load(f))

    collisions = []
    for kind, values in new.items():
        used = entries(hist, kind, COOLDOWN_DAYS[kind])
        seen_in_file = {}
        for v in values:
            k = norm(v)
            if k in used:
                collisions.append((kind, v, f"already used on {used[k][1]}"))
            elif k in seen_in_file:
                collisions.append((kind, v, "duplicated within this edition"))
            else:
                seen_in_file[k] = True

    if collisions:
        print(f"FAIL — {len(collisions)} collision(s):", file=sys.stderr)
        for kind, val, why in collisions:
            print(f"  [{kind}] {str(val)[:100]}\n      {why}", file=sys.stderr)
        print("\nReplace these before sending.", file=sys.stderr)
        return 1

    print("OK — nothing in this edition has been used before.")
    return 0


def cmd_record(args):
    hist = load()
    with open(args.edition, encoding="utf-8") as f:
        ed = json.load(f)

    stem = os.path.splitext(os.path.basename(args.edition))[0]
    # Accept 2026-09-03.json and 2026-09-03-2.json alike; the date is the
    # prefix, and the issue number distinguishes editions within a day.
    m = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
    if not m:
        print(f"edition filename must start with YYYY-MM-DD: {stem}", file=sys.stderr)
        return 2
    day = m.group(1)
    issue = ed.get("issue")
    hist.setdefault("editions", [])
    # Re-recording the same issue replaces it; a second issue on the same day
    # is kept alongside the first, so nothing it used is ever forgotten.
    hist["editions"] = [x for x in hist["editions"]
                        if not (x.get("date") == day and x.get("issue") == issue)]

    entry = {"date": day, "issue": issue}
    entry.update(harvest(ed))
    if args.message_id:
        entry["gmail_message_id"] = args.message_id
    hist["editions"].append(entry)
    hist["editions"].sort(key=lambda x: x.get("date", ""))

    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist, f, indent=2, ensure_ascii=False)
    print(f"recorded {day} ({len(hist['editions'])} editions on file)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show").set_defaults(fn=cmd_show)

    c = sub.add_parser("check")
    c.add_argument("edition")
    c.set_defaults(fn=cmd_check)

    r = sub.add_parser("record")
    r.add_argument("edition")
    r.add_argument("--message-id", default=None)
    r.set_defaults(fn=cmd_record)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
