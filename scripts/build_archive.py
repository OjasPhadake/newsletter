#!/usr/bin/env python3
"""Render editions/ as a browsable web archive.

The archive is the demo. Nobody forks a newsletter generator on faith — they
want to read one first — and every issue is already sitting in editions/ as
structured data. This turns that into a static site: an index, one page per
issue, and a feed.

Issue pages are the *same* HTML the email uses, straight out of build_email,
so the archive can never drift from what actually landed in the inbox.

    python3 scripts/build_archive.py                 # -> site/
    python3 scripts/build_archive.py --out public
"""
import argparse
import glob
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_email
import config as _config

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITIONS = os.path.join(HERE, "editions")


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def slug(path):
    return os.path.splitext(os.path.basename(path))[0]


def issue_date(name):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""


def teaser(ed, cfg):
    """A few headlines, so the index says what is actually in each issue."""
    out = []
    for sec in cfg["sections"]:
        val = ed.get(sec["key"])
        if not val:
            continue
        if isinstance(val, list):
            for it in val[:1]:
                t = (it.get("headline") or it.get("title")) if isinstance(it, dict) else None
                if t:
                    out.append((sec["accent"], t))
        elif isinstance(val, dict) and val.get("title"):
            out.append((sec["accent"], val["title"]))
    return out[:4]


def index_css(cfg):
    L, D, SERIF, SANS = (build_email.L, build_email.D,
                         build_email.SERIF, build_email.SANS)
    acc = "\n".join(f".{k}{{color:{v[0]}}}" for k, v in build_email.ACCENTS.items())
    acc_d = "\n".join(f".{k}{{color:{v[1]}}}" for k, v in build_email.ACCENTS.items())
    return f"""
*{{box-sizing:border-box}}
body{{margin:0;background:{L['paper']};color:{L['ink']};font:400 16px/1.6 {SANS};
-webkit-font-smoothing:antialiased}}
a{{color:inherit}}
.wrap{{max-width:640px;margin:0 auto;padding:40px 22px 72px}}
.rule{{height:3px;background:{L['ink']}}}
.hair{{height:1px;background:{L['rule']}}}
.ttl{{font:400 34px/1.05 {SERIF};letter-spacing:.2em;text-transform:uppercase;
text-align:center;margin:26px 0 0}}
.tag{{font:400 14px/1.6 {SANS};color:{L['soft']};text-align:center;margin:14px 0 0}}
.count{{font:600 12px/1 {SANS};letter-spacing:.14em;text-transform:uppercase;
color:{L['faint']};margin:34px 0 10px}}
.issue{{display:block;text-decoration:none;padding:20px 0;border-top:1px solid {L['rule']}}}
.issue:hover .dt{{text-decoration:underline}}
.dt{{font:600 18px/1.35 {SERIF}}}
.no{{font:600 11px/1 {SANS};letter-spacing:.12em;color:{L['faint']};
text-transform:uppercase;margin-left:8px}}
.qt{{font:400 italic 15px/1.55 {SERIF};color:{L['soft']};margin:8px 0 0}}
.heads{{margin:10px 0 0;padding:0;list-style:none}}
.heads li{{font:400 14px/1.55 {SANS};color:{L['soft']};padding:1px 0}}
.heads b{{font-weight:600}}
.foot{{margin:56px 0 0;font:400 13px/1.7 {SANS};color:{L['faint']};text-align:center}}
{acc}
@media (prefers-color-scheme:dark){{
body{{background:{D['paper']};color:{D['ink']}}}
.rule{{background:{D['ink']}}}
.hair,.issue{{border-color:{D['rule']}}}
.tag,.qt,.heads li{{color:{D['soft']}}}
.count,.no,.foot{{color:{D['faint']}}}
{acc_d}
}}
"""


def render_index(issues, cfg):
    paper = cfg["newsletter"]
    rows = []
    for it in issues:
        ed, name = it["ed"], it["slug"]
        q = ed.get("quote") or {}
        heads = "".join(
            f'<li><b class="{a}">&middot;</b> {e(t)}</li>' for a, t in it["teaser"])
        num = (f'<span class="no">No. {e(ed["issue"])}</span>'
               if ed.get("issue") else "")
        quote = (f'<p class="qt">&ldquo;{e(q["text"][:150])}&rdquo; &mdash; '
                 f'{e(q.get("author", "Unknown"))}</p>' if q.get("text") else "")
        rows.append(
            f'<a class="issue" href="{e(name)}.html">'
            f'<div class="dt">{e(ed.get("date_line") or it["date"])}{num}</div>'
            f'{quote}<ul class="heads">{heads}</ul></a>')

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(paper['title'])} &mdash; archive</title>
<meta name="description" content="{e(paper['tagline'])}">
<link rel="alternate" type="application/rss+xml" title="{e(paper['title'])}" href="feed.xml">
<style>{index_css(cfg)}</style>
</head>
<body><div class="wrap">
<div class="rule"></div>
<h1 class="ttl">{e(paper['title'])}</h1>
<p class="tag">{e(paper['tagline'])}</p>
<div class="count">{len(issues)} issue{'s' if len(issues) != 1 else ''}
&nbsp;&middot;&nbsp; <a href="feed.xml">RSS</a></div>
{''.join(rows)}
<div class="hair"></div>
<p class="foot">Assembled every morning by an agent, from Hacker News, the
day&rsquo;s reporting and the labs&rsquo; own research blogs.<br>
Nothing in it ever repeats &mdash; that part is enforced in code.<br>
<a href="{e(cfg['sender']['repo'])}">Source and setup on GitHub</a></p>
</div></body></html>"""


def render_feed(issues, cfg):
    paper, site = cfg["newsletter"], cfg["newsletter"]["site_url"].rstrip("/")
    items = []
    for it in issues[:50]:
        ed, link = it["ed"], f"{site}/{it['slug']}.html" if site else f"{it['slug']}.html"
        # Literal characters, not HTML entities: &mdash; and friends are
        # undefined in XML and make the feed unparseable.
        heads = " \u00b7 ".join(e(t) for _, t in it["teaser"])
        try:
            when = datetime.strptime(it["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            pub = f"<pubDate>{format_datetime(when)}</pubDate>"
        except ValueError:
            pub = ""
        items.append(
            f"<item><title>{e(paper['title'])} \u2014 "
            f"{e(ed.get('date_line') or it['date'])}</title>"
            f"<link>{e(link)}</link><guid isPermaLink=\"false\">{e(it['slug'])}</guid>"
            f"{pub}<description>{heads}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>'
            f"<title>{e(paper['title'])}</title>"
            f"<link>{e(site or '')}</link>"
            f"<description>{e(paper['tagline'])}</description>"
            f"{''.join(items)}</channel></rss>")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=os.path.join(HERE, "site"))
    p.add_argument("--editions", default=EDITIONS)
    args = p.parse_args()

    cfg = _config.load()
    os.makedirs(args.out, exist_ok=True)

    issues = []
    for path in sorted(glob.glob(os.path.join(args.editions, "*.json")), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                ed = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  skipped {os.path.basename(path)}: {exc}", file=sys.stderr)
            continue
        name = slug(path)
        issues.append({"ed": ed, "slug": name, "date": issue_date(name),
                       "teaser": teaser(ed, cfg)})
        with open(os.path.join(args.out, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(build_email.build(ed, cfg))

    # Newest first, and a second issue on a day sorts above the first.
    issues.sort(key=lambda i: (i["date"], i["slug"]), reverse=True)

    for name, body in (("index.html", render_index(issues, cfg)),
                       ("feed.xml", render_feed(issues, cfg))):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            f.write(body)

    print(f"{len(issues)} issue(s) -> {args.out}")
    return 0 if issues else 1


if __name__ == "__main__":
    sys.exit(main())
