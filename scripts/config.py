#!/usr/bin/env python3
"""Read newsletter.toml, and survive it being absent or wrong.

Every other script imports `load()` from here. The defaults below reproduce
the newsletter exactly as it ran before this file existed, and anything
missing, misspelled or unparseable falls back to them with a warning on
stderr. A config mistake must never be the reason a morning send fails.

    python3 scripts/config.py           # what is actually in effect
    python3 scripts/config.py --cron    # the cron line for your send time
    python3 scripts/config.py --get reader.email
"""
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "newsletter.toml")

DEFAULTS = {
    "newsletter": {
        "title": "The Morning",
        "tagline": "Your daily brief: a quote, the best of Hacker News, "
                   "markets, and a little something new.",
        "timezone": "Asia/Kolkata",
        "send_time": "07:00",
        "site_url": "",
    },
    "reader": {
        "name": "Ojas",
        "email": "ch22b007@smail.iitm.ac.in",
        "about": "a chemical engineering / data science student at IIT Madras",
    },
    "sender": {
        "from_name": "The Morning",
        "provider": "gmail",
        "contact": "ch22b007@smail.iitm.ac.in",
        "repo": "https://github.com/OjasPhadake/newsletter",
    },
    "sections": [
        {"key": "hn", "title": "Hacker News · Last 24 Hours", "accent": "pine",
         "render": "hn", "brief": "The Hacker News brief"},
        {"key": "markets", "title": "Markets · India & World", "accent": "indigo",
         "render": "markets", "brief": "The markets brief"},
        {"key": "trends", "title": "Trends & Signals", "accent": "moss",
         "render": "stories", "brief": "The trends brief"},
        {"key": "research", "title": "From the Research Desk", "accent": "plum",
         "render": "stories_title", "brief": "The research brief"},
        {"key": "wild", "title": "Wonderfully Odd Ideas", "accent": "amber",
         "render": "stories", "brief": "The odd-ideas brief"},
        {"key": "learn", "title": "One Thing to Learn", "accent": "clay",
         "render": "learn", "brief": "The learn brief"},
        {"key": "ideas", "title": "Ten Ideas", "accent": "iris",
         "render": "ideas", "brief": "The ideas brief"},
    ],
}

# Renderers build_email.py knows about, and accents the stylesheet defines.
RENDERERS = {"hn", "markets", "stories", "stories_title", "learn", "ideas"}
ACCENTS = {"amber", "pine", "indigo", "plum", "clay", "moss", "iris"}

_cache = None


def _warn(msg):
    print(f"config: {msg}", file=sys.stderr)


def _sections(raw):
    """Validate the section list, dropping only the entries that are broken."""
    out = []
    seen = set()
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            _warn(f"section {i} is not a table; ignoring it")
            continue
        key = str(s.get("key", "")).strip()
        if not key:
            _warn(f"section {i} has no key; ignoring it")
            continue
        if key in seen:
            _warn(f"section {key!r} is listed twice; keeping the first")
            continue
        render = str(s.get("render", "stories"))
        if render not in RENDERERS:
            _warn(f"section {key!r} wants renderer {render!r}, which does not "
                  f"exist; using 'stories'. Known: {', '.join(sorted(RENDERERS))}")
            render = "stories"
        accent = str(s.get("accent", "moss"))
        if accent not in ACCENTS:
            _warn(f"section {key!r} wants accent {accent!r}, which is not in the "
                  f"palette; using 'moss'. Known: {', '.join(sorted(ACCENTS))}")
            accent = "moss"
        seen.add(key)
        out.append({"key": key, "title": str(s.get("title", key)),
                    "accent": accent, "render": render,
                    "brief": str(s.get("brief", ""))})
    if not out:
        _warn("no usable sections; falling back to the built-in running order")
        return [dict(s) for s in DEFAULTS["sections"]]
    return out


def load(path=None, force=False):
    """The effective config: file values over defaults, never a hard failure."""
    global _cache
    if _cache is not None and not force and path is None:
        return _cache

    cfg = {k: (dict(v) if isinstance(v, dict) else [dict(x) for x in v])
           for k, v in DEFAULTS.items()}
    p = path or CONFIG
    raw = {}
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                raw = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            _warn(f"could not read {os.path.basename(p)} ({exc}); using defaults")
            raw = {}
    elif path is not None:
        _warn(f"{p} does not exist; using defaults")

    for table in ("newsletter", "reader", "sender"):
        got = raw.get(table)
        if got is None:
            continue
        if not isinstance(got, dict):
            _warn(f"[{table}] is not a table; using defaults for it")
            continue
        for k, v in got.items():
            if k not in cfg[table]:
                _warn(f"[{table}] has an unknown key {k!r}; ignoring it")
                continue
            cfg[table][k] = v

    if isinstance(raw.get("sections"), list):
        cfg["sections"] = _sections(raw["sections"])
    elif "sections" in raw:
        _warn("[[sections]] is not a list; using the built-in running order")

    if path is None:
        _cache = cfg
    return cfg


def user_agent(cfg=None):
    """One User-Agent for every fetcher, so services can identify us."""
    cfg = cfg or load()
    return {"User-Agent": "Mozilla/5.0 (compatible; daily-newsletter/1.0; "
                          f"+{cfg['sender']['repo']})"}


def cron_line(cfg=None):
    """The UTC cron for the configured local send time.

    Reported as-is. The workflow deliberately runs its cron early to offset
    GitHub's dispatch lag; see the comment in daily.yml.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    cfg = cfg or load()
    try:
        hh, mm = (int(x) for x in str(cfg["newsletter"]["send_time"]).split(":"))
        tz = ZoneInfo(cfg["newsletter"]["timezone"])
    except (ValueError, KeyError, Exception):  # noqa: B014 - ZoneInfo raises broadly
        return None
    local = datetime.now(tz).replace(hour=hh, minute=mm, second=0, microsecond=0)
    utc = local.astimezone(ZoneInfo("UTC"))
    early = utc - timedelta(hours=5)
    return (f"{utc.minute} {utc.hour} * * *",
            f"{early.minute} {early.hour} * * *")


def missing_briefs(cfg=None, prompt=None):
    """Sections whose brief heading is not actually in PROMPT.md.

    A section without a brief renders fine and reads badly: the layout is the
    easy half, and the agent has nothing telling it what belongs there.
    """
    cfg = cfg or load()
    path = prompt or os.path.join(HERE, "PROMPT.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    return [s for s in cfg["sections"]
            if s["brief"] and f"# {s['brief']}" not in text]


def main():
    cfg = load()
    if "--cron" in sys.argv:
        got = cron_line(cfg)
        if not got:
            print("could not read send_time/timezone", file=sys.stderr)
            return 2
        exact, early = got
        print(f"send_time {cfg['newsletter']['send_time']} "
              f"{cfg['newsletter']['timezone']}")
        print(f"  exact UTC cron:            '{exact}'")
        print(f"  what daily.yml should use: '{early}'   "
              f"(5h early, offsets GitHub's dispatch lag)")
        return 0
    if "--get" in sys.argv:
        dotted = sys.argv[sys.argv.index("--get") + 1]
        node = cfg
        for part in dotted.split("."):
            node = node[part] if isinstance(node, dict) else node[int(part)]
        print(node if not isinstance(node, (dict, list)) else
              " ".join(str(x.get("key", x)) for x in node)
              if isinstance(node, list) else node)
        return 0

    print(f"config: {CONFIG if os.path.exists(CONFIG) else '(missing — defaults)'}\n")
    for table in ("newsletter", "reader", "sender"):
        print(f"[{table}]")
        for k, v in cfg[table].items():
            print(f"  {k:<10} {v!r}")
    print("\n[[sections]] — the running order")
    for i, s in enumerate(cfg["sections"], 1):
        print(f"  {i}. {s['key']:<9} {s['title']:<30} "
              f"{s['accent']:<7} {s['render']}")

    gaps = missing_briefs(cfg)
    if gaps:
        print("\nWARNING: no editorial brief in PROMPT.md for:")
        for s in gaps:
            print(f"  {s['key']} — add a section headed '### {s['brief']}'")
        print("The layout will render; the writing will have nothing to go on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
