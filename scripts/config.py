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
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "newsletter.toml")
TEMPLATES = os.path.join(HERE, "templates")

DEFAULTS = {
    "newsletter": {
        "title": "The Morning",
        "tagline": "Your daily brief: a quote, the best of Hacker News, "
                   "markets, and a little something new.",
        "timezone": "Asia/Kolkata",
        "send_time": "07:00",
        "site_url": "",
        "template": "morning",
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

# Renderers build_email.py knows about, and accents every template defines.
RENDERERS = {"hn", "markets", "stories", "stories_title", "learn", "ideas"}
ACCENTS = {"amber", "pine", "indigo", "plum", "clay", "moss", "iris"}

# The look. Every key has a default here, so a template file only has to say
# what it changes — and a template that goes missing degrades to `morning`
# rather than taking the send down with it.
DEFAULT_TEMPLATE = {
    "name": "Morning",
    "description": "Warm paper and ink, serif masthead, numbered section rules.",
    "fonts": {
        "serif": "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,"
                 "'Times New Roman',serif",
        "sans": "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,"
                "sans-serif",
        "heading": "serif",     # which stack headings use: serif or sans
        "body": "sans",         # and body copy
    },
    "light": {"paper": "#FBF8F3", "card": "#FFFDFA", "ink": "#23272B",
              "soft": "#6E6A63", "faint": "#94908A", "rule": "#E6DED1"},
    "dark":  {"paper": "#15181B", "card": "#1C2025", "ink": "#E9E5DD",
              "soft": "#A39E95", "faint": "#7C776F", "rule": "#31363C"},
    "accents": {
        "amber":  ["#A8792F", "#DCBA72"],
        "pine":   ["#2F6B62", "#77B8AE"],
        "indigo": ["#47527A", "#96A2CC"],
        "plum":   ["#77496B", "#C293B4"],
        "clay":   ["#AF5C36", "#E29268"],
        "moss":   ["#5A6B33", "#AFC17A"],
        "iris":   ["#5B4B8A", "#A99AD6"],
    },
    "market": {"up": "#2F7A52", "down": "#B04A3C",
               "up_dark": "#7FBF9A", "down_dark": "#E08A7C"},
    "masthead": {"size": 36, "weight": 400, "leading": "1.05",
                 "tracking": ".22em", "transform": "uppercase",
                 "rule": 3, "small_size": 30, "small_tracking": ".16em"},
    "section": {"number": True, "bar": 2, "size": 12,
                "tracking": ".19em", "transform": "uppercase"},
    "quote": {"style": "card", "mark": True, "italic": True, "size": 21},
    "body": {"size": 15, "leading": "1.55", "h1": 18, "h2": 17,
             "radius": 0, "link_underline": False},
}

_cache = None
_tpl_cache = {}


def _merge(base, over):
    """Deep-merge a template file over the defaults."""
    out = dict(base)
    for k, v in (over or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def template_names():
    if not os.path.isdir(TEMPLATES):
        return ["morning"]
    got = sorted(os.path.splitext(os.path.basename(p))[0]
                 for p in os.listdir(TEMPLATES) if p.endswith(".toml"))
    return got or ["morning"]


def load_template(name=None, cfg=None):
    """A complete look, defaults filled in. Never raises."""
    name = name or (cfg or load())["newsletter"]["template"]
    name = str(name).strip() or "morning"
    if name in _tpl_cache:
        return _tpl_cache[name]

    raw = {}
    path = os.path.join(TEMPLATES, f"{os.path.basename(name)}.toml")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                raw = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            _warn(f"template {name!r} is unreadable ({exc}); using the default look")
    elif name != "morning":
        _warn(f"template {name!r} not found in templates/; using the default look. "
              f"Available: {', '.join(template_names())}")

    tpl = _merge(DEFAULT_TEMPLATE, raw)
    tpl["id"] = name

    # Colours go straight into a stylesheet, so a malformed one is invisible
    # until someone opens the email. Check them here instead.
    def ok_colour(v):
        return isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{3,8}", v.strip())

    for table in ("light", "dark"):
        for k, default in DEFAULT_TEMPLATE[table].items():
            if not ok_colour(tpl[table].get(k)):
                _warn(f"template {name!r}: [{table}].{k} = "
                      f"{tpl[table].get(k)!r} is not a colour; using {default}")
                tpl[table][k] = default

    for k, default in DEFAULT_TEMPLATE["market"].items():
        if not ok_colour(tpl["market"].get(k)):
            _warn(f"template {name!r}: [market].{k} is not a colour; using {default}")
            tpl["market"][k] = default

    # A template that forgot an accent would raise deep inside the renderer.
    for k, v in DEFAULT_TEMPLATE["accents"].items():
        got = tpl["accents"].get(k)
        if not (isinstance(got, (list, tuple)) and len(got) == 2
                and all(ok_colour(x) for x in got)):
            _warn(f"template {name!r} has no usable accent {k!r}; keeping the default")
            tpl["accents"][k] = list(v)
    _tpl_cache[name] = tpl
    return tpl


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
    tpl = load_template(cfg=cfg)
    print(f"\n[template] {tpl['id']} — {tpl['name']}: {tpl['description']}")
    print(f"  available: {', '.join(template_names())}")

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
