#!/usr/bin/env python3
"""Duplicate guard for The Morning.

Nothing in this newsletter should ever repeat: not a quote, not an idea, not a
prompt, not a story. Relying on the agent to remember that across months of
issues is not a plan, so it is enforced here instead. `check` exits non-zero
and names every collision; the daily run is not allowed to send until it passes.

The first version of this only remembered URLs, which meant the same story
sailed through under a different outlet's link — the Ordinary's $175 banana ran
twice in two days, Chili's fake loan office twice in three, Houston's airport
twice in four. So it now remembers what an item was *about*: the subject line of
every story, matched loosely, plus the brands named in the odd-ideas section.

The matching itself lives in `norepeat.py`, which knows nothing about
newsletters and is useful to any job that runs every day and must not repeat
itself. This file is the newsletter's half: what to harvest out of an edition,
and what to tell the writer about it.

    python3 scripts/history.py brief                     # what tomorrow may not use
    python3 scripts/history.py show
    python3 scripts/history.py check editions/2026-09-04.json
    python3 scripts/history.py record editions/2026-09-04.json
    python3 scripts/history.py backfill                  # rebuild from editions/
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import norepeat
from norepeat import Guard, dedupe, names, norm_name

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(HERE, "state", "history.json")
EDITIONS = os.path.join(HERE, "editions")

# How long each kind of thing stays "used". None means forever.
COOLDOWN_DAYS = {
    "quote_text":   None,   # a quote is never repeated, full stop
    "quote_author": 90,
    "idea_text":    None,   # nor is an idea
    "idea_prompt":  120,
    "hn_id":        None,
    "link":         45,
    "subject":      None,   # what a story was about, however it was worded
    "brand":        60,     # whose stunt an odd-ideas item was
    "brand_mention": 60,    # brands named in passing in an odd-ideas bullet
}

# Recorded so that a brand mentioned in passing today blocks a headline about
# it tomorrow — Burger King turned up in a Friday bullet and headlined Monday.
# Never checked in its own right: bullet copy names cities, agencies and
# people, and blocking on all of that would reject good stories.
NOT_CHECKED = {"brand_mention"}
ALSO_CHECK = {"brand": ["brand_mention"]}

# Kinds matched loosely as well as exactly: a reworded repeat is still a repeat.
FUZZY = {"subject"}

# Possessives are noise in a brand name; they are signal nowhere else.
KEY_NORM = {"brand": norm_name, "brand_mention": norm_name}

# Newsletter-specific additions to norepeat's generic ignore list: places,
# platforms and awards that turn up in campaign copy without naming a brand.
NOT_A_BRAND = norepeat.NOT_A_NAME | set("""
instagram reddit youtube tiktok twitter facebook linkedin snapchat whatsapp
threads twitch spotify google apple amazon microsoft
london paris tokyo delhi mumbai manhattan brooklyn america american americans
us usa uk britain british india indian europe european china chinese japan
japanese earth world sunset boulevard south north east west
cannes lions bronze silver gold grand prix effie clio dandad webby
q1 q2 q3 q4 ai llm llms gdp cpi rbi
""".split())

DOMAIN_WINDOW_DAYS = 30


def guard():
    return Guard(HISTORY, cooldowns=COOLDOWN_DAYS, fuzzy=FUZZY,
                 not_checked=NOT_CHECKED, also_check=ALSO_CHECK,
                 key_norm=KEY_NORM, entries_field="editions")


def brands(text, actor_only=False):
    return names(text, first_only=actor_only, ignore=NOT_A_BRAND)


def harvest(ed):
    """Pull the uniqueness-relevant fields out of an edition JSON."""
    q = ed.get("quote") or {}
    ideas = ed.get("ideas") or {}
    items = ideas.get("items") or []
    learn = ed.get("learn") or {}

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

    # What each story was about. Hacker News is left out on purpose: it is
    # already keyed on the item id, and the five are whatever the front page
    # voted for. Markets are left out because they recur by design.
    subjects = []
    for key in ("trends", "wild", "research"):
        for it in ed.get(key) or []:
            subjects.append(it.get("subject") or it.get("headline") or it.get("title"))
    if learn.get("title"):
        subjects.append(learn.get("subject") or learn["title"])

    # Brands only from the odd-ideas section. Trends recur legitimately —
    # India, Google and the RBI are in the news most weeks — but the same
    # brand's stunt twice in a month is exactly what went wrong.
    actors, mentions = [], []
    for it in ed.get("wild") or []:
        actors.extend(it.get("entities") or [])
        actors.extend(brands(it.get("headline"), actor_only=True))
        mentions.extend(brands(" ".join(it.get("bullets") or [])))

    return {
        "quote_text":   [q.get("text")] if q.get("text") else [],
        "quote_author": [q.get("author")] if q.get("author") else [],
        "idea_text":    [idea_text(i) for i in items if idea_text(i)],
        "idea_prompt":  [ideas["prompt"]] if ideas.get("prompt") else [],
        "hn_id":        [re.sub(r".*id=", "", s.get("hn_url", ""))
                         for s in ed.get("hn") or [] if s.get("hn_url")],
        "link":         [u for u in links if u],
        "subject":      [s for s in subjects if s],
        "brand":        dedupe(actors, norm_name),
        "brand_mention": dedupe(mentions, norm_name),
    }


def sections_of(ed):
    """(section, subject) pairs, for the briefing."""
    out = []
    for key in ("trends", "wild", "research"):
        for it in ed.get(key) or []:
            t = it.get("headline") or it.get("title")
            if t:
                out.append((key, t))
    learn = ed.get("learn") or {}
    if learn.get("title"):
        out.append(("learn", learn["title"]))
    return out


def entry_for(path, ed):
    stem = os.path.splitext(os.path.basename(path))[0]
    # Accept 2026-09-03.json and 2026-09-03-2.json alike; the date is the
    # prefix, and the issue number distinguishes editions within a day.
    m = re.match(r"(\d{4}-\d{2}-\d{2})", stem)
    if not m:
        return None
    entry = {"date": m.group(1), "issue": ed.get("issue")}
    entry.update(harvest(ed))
    # Kept alongside the flat subject list so `brief` can say which section a
    # subject ran in without reopening every edition file.
    entry["section_subjects"] = [list(x) for x in sections_of(ed)]
    # Where the editorial sections went shopping. Research and markets are
    # excluded: arxiv and the lab blogs are supposed to recur, a campaign
    # listicle is not.
    entry["editorial_domains"] = sorted({
        urlparse(it.get("url") or "").netloc.replace("www.", "")
        for key in ("trends", "wild") for it in ed.get(key) or []
        if it.get("url")} - {""})
    return entry


def cmd_show(_):
    g = guard()
    eds = g.load().get("editions", [])
    print(f"{len(eds)} edition(s) recorded")
    for kind, days in COOLDOWN_DAYS.items():
        used = g.entries(kind, days)
        window = "ever" if days is None else f"last {days}d"
        print(f"\n{kind} ({window}) — {len(used)}")
        for _, (val, when) in sorted(used.items(), key=lambda kv: kv[1][1], reverse=True)[:12]:
            print(f"  {when}  {str(val)[:90]}")
    return 0


def cmd_brief(args):
    """The one to read before choosing anything.

    `show` lists mostly URLs, which is no help when the question is "has this
    story run before". This prints the things a writer actually needs to avoid.
    """
    g = guard()
    eds = g.load().get("editions", [])
    if not eds:
        print("No editions on record yet — nothing to avoid.")
        return 0

    days = args.days
    cutoff = date.today() - timedelta(days=days)

    def recent(kind, within):
        return sorted(g.entries(kind, within).values(),
                      key=lambda v: str(v[1]), reverse=True)

    def within(ed, window):
        try:
            return datetime.strptime(ed["date"], "%Y-%m-%d").date() >= window
        except (KeyError, ValueError):
            return False

    print(f"THE MORNING — what today may not repeat  ({len(eds)} editions on record)")
    print("Anything below has already been sent. Pick something else; rewording is not a fix.")

    print(f"\n── SUBJECTS ALREADY COVERED (last {days}d) " + "─" * 20)
    print("A story counts as used however it is worded, and whoever published it.")
    by_day = {}
    for ed in eds:
        if not within(ed, cutoff):
            continue
        by_day.setdefault(ed["date"], []).extend(
            (ed.get("section_subjects") or [])
            or [["", s] for s in ed.get("subject") or []])
    for day in sorted(by_day, reverse=True):
        print(f"  {day}")
        for sec, subj in by_day[day]:
            print(f"      {sec:<9}{str(subj)[:88]}")

    print(f"\n── BRANDS USED IN ODD IDEAS (last {COOLDOWN_DAYS['brand']}d, blocked) " + "─" * 8)
    b = recent("brand", COOLDOWN_DAYS["brand"])
    print("  whose stunt it was: "
          + (", ".join(sorted({v for v, _ in b})) if b else "(none)"))
    m = {v for v, _ in recent("brand_mention", COOLDOWN_DAYS["brand_mention"])}
    print(f"  Also blocked: {len(m)} more brands named in passing inside past bullets "
          "(check names any collision).")

    print(f"\n── SOURCE DOMAINS (last {DOMAIN_WINDOW_DAYS}d) " + "─" * 28)
    print("Not blocked, but a domain you keep returning to is a well running dry.")
    doms = Counter()
    dom_cut = date.today() - timedelta(days=DOMAIN_WINDOW_DAYS)
    for ed in eds:
        if within(ed, dom_cut):
            doms.update(ed.get("editorial_domains") or [])
    if not doms:
        print("  (none yet)")
    for host, n in doms.most_common(15):
        flag = "  <- going back to this well; find another source" if n >= 3 else ""
        print(f"  {n:>2}  {host}{flag}")

    print(f"\n── QUOTE AUTHORS (last {COOLDOWN_DAYS['quote_author']}d, blocked) " + "─" * 14)
    print("  " + (", ".join(sorted({v for v, _ in recent("quote_author", 90)})) or "(none)"))

    print(f"\n── IDEAS PROMPTS (last {COOLDOWN_DAYS['idea_prompt']}d, blocked) " + "─" * 15)
    for v, when in recent("idea_prompt", COOLDOWN_DAYS["idea_prompt"]):
        print(f"  {when}  {v}")

    print("\n── LEARN, MOST RECENT FIRST " + "─" * 33)
    print("Rotate the flavour: everyday systems / origin stories / science of")
    print("ordinary things / human behaviour. Do not run two of a kind back to back.")
    for ed in sorted(eds, key=lambda e: e.get("date", ""), reverse=True)[:10]:
        for sec, subj in ed.get("section_subjects") or []:
            if sec == "learn":
                print(f"  {ed['date']}  {str(subj)[:88]}")

    print("\n── HACKER NEWS IDS ALREADY RUN " + "─" * 30)
    ids = sorted({v for v, _ in recent("hn_id", None)})
    print(f"  {len(ids)} ids on record" + (f" — most recent: {', '.join(ids[-10:])}" if ids else ""))
    return 0


def cmd_check(args):
    with open(args.edition, encoding="utf-8") as f:
        new = harvest(json.load(f))

    collisions = guard().check(new)
    if collisions:
        print(f"FAIL — {len(collisions)} collision(s):", file=sys.stderr)
        for c in collisions:
            print(f"  [{c.kind}] {str(c.value)[:100]}\n      {c.why}", file=sys.stderr)
        print("\nReplace these before sending. Pick a different story — rewording",
              file=sys.stderr)
        print("the headline is not a fix, and neither is a different outlet's link.",
              file=sys.stderr)
        return 1

    print("OK — nothing in this edition has been used before.")
    return 0


def cmd_record(args):
    with open(args.edition, encoding="utf-8") as f:
        ed = json.load(f)

    entry = entry_for(args.edition, ed)
    if entry is None:
        stem = os.path.basename(args.edition)
        print(f"edition filename must start with YYYY-MM-DD: {stem}", file=sys.stderr)
        return 2

    g = guard()
    # Re-recording the same issue replaces it; a second issue on the same day
    # is kept alongside the first, so nothing it used is ever forgotten.
    prior = [x for x in g.load().get("editions", [])
             if x.get("date") == entry["date"] and x.get("issue") == entry["issue"]]
    if prior and prior[0].get("gmail_message_id"):
        entry["gmail_message_id"] = prior[0]["gmail_message_id"]
    if args.message_id:
        entry["gmail_message_id"] = args.message_id

    state = g.record(entry, replace_on=("date", "issue"))
    state["editions"].sort(key=lambda x: (x.get("date", ""), x.get("issue") or 0))
    g.save(state)
    print(f"recorded {entry['date']} ({len(state['editions'])} editions on file)")
    return 0


def cmd_backfill(_):
    """Rebuild history from editions/, keeping any message ids already stored.

    Needed once, because editions sent before subjects and brands were tracked
    have none on record — and until they do, the guard is still blind to them.
    """
    g = guard()
    old = {(e.get("date"), e.get("issue")): e for e in g.load().get("editions", [])}
    rebuilt = []
    for path in sorted(glob.glob(os.path.join(EDITIONS, "*.json"))):
        with open(path, encoding="utf-8") as f:
            ed = json.load(f)
        entry = entry_for(path, ed)
        if entry is None:
            print(f"  skipped (no date in name): {os.path.basename(path)}")
            continue
        was = old.get((entry["date"], entry["issue"])) or {}
        if was.get("gmail_message_id"):
            entry["gmail_message_id"] = was["gmail_message_id"]
        rebuilt.append(entry)
        print(f"  {entry['date']} #{entry['issue']}  "
              f"{len(entry['subject'])} subjects, {len(entry['brand'])} brands")

    done = {(e["date"], e["issue"]) for e in rebuilt}
    for k, v in old.items():
        if k not in done:
            print(f"  WARNING: {k} was on record but has no edition file; keeping it")
            rebuilt.append(v)
    rebuilt.sort(key=lambda x: (x.get("date", ""), x.get("issue") or 0))

    g.save({"editions": rebuilt})
    print(f"rebuilt {len(rebuilt)} edition(s)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show").set_defaults(fn=cmd_show)

    b = sub.add_parser("brief")
    b.add_argument("--days", type=int, default=45)
    b.set_defaults(fn=cmd_brief)

    c = sub.add_parser("check")
    c.add_argument("edition")
    c.set_defaults(fn=cmd_check)

    r = sub.add_parser("record")
    r.add_argument("edition")
    r.add_argument("--message-id", default=None)
    r.set_defaults(fn=cmd_record)

    sub.add_parser("backfill").set_defaults(fn=cmd_backfill)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
