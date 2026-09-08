#!/usr/bin/env python3
"""Render one issue in every template, side by side, so you can pick one.

Choosing a look from a list of adjectives is guesswork. This builds the same
edition in each template and an index that switches between them, so the
decision is made by looking.

    python3 scripts/preview_templates.py            # newest edition
    python3 scripts/preview_templates.py --edition editions/2026-09-05.json
    python3 scripts/preview_templates.py --out /tmp/looks
"""
import argparse
import glob
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_email
import config as _config

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def picker(names, cfg, current):
    cards = []
    for n in names:
        t = _config.load_template(n)
        swatch = "".join(
            f'<i style="background:{t["accents"][k][0]}"></i>'
            for k in ("pine", "indigo", "moss", "plum", "amber", "clay", "iris"))
        mark = ' <b>&larr; in use</b>' if n == current else ""
        cards.append(
            f'<a class="card" href="{e(n)}.html" target="view">'
            f'<div class="paper" style="background:{t["light"]["paper"]};'
            f'color:{t["light"]["ink"]};border-color:{t["light"]["rule"]}">Aa</div>'
            f'<div class="meta"><h3>{e(t["name"])}<code>{e(n)}</code>{mark}</h3>'
            f'<p>{e(t["description"])}</p><div class="sw">{swatch}</div></div></a>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{e(cfg['newsletter']['title'])} &mdash; templates</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font:400 15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',
Helvetica,Arial,sans-serif;background:#fff;color:#111827;display:flex;
height:100vh;overflow:hidden}}
.side{{width:340px;flex:0 0 340px;overflow-y:auto;border-right:1px solid #E5E7EB;
padding:22px}}
h1{{font:700 19px/1.3 inherit;margin:0 0 4px}}
.lede{{color:#6B7280;font-size:13px;margin:0 0 18px}}
.card{{display:flex;gap:13px;padding:12px;border:1px solid #E5E7EB;border-radius:10px;
margin:0 0 10px;text-decoration:none;color:inherit}}
.card:hover{{border-color:#9CA3AF;background:#F9FAFB}}
.paper{{width:52px;height:52px;flex:0 0 52px;border:1px solid;border-radius:7px;
display:flex;align-items:center;justify-content:center;font:600 19px/1 Georgia,serif}}
.meta h3{{font:600 14px/1.3 inherit;margin:2px 0 3px}}
.meta code{{font:500 11px/1 ui-monospace,Menlo,monospace;color:#6B7280;
margin-left:6px;background:#F3F4F6;padding:2px 5px;border-radius:4px}}
.meta b{{font-size:11px;color:#B45309}}
.meta p{{margin:0 0 7px;font-size:12.5px;line-height:1.5;color:#6B7280}}
.sw i{{display:inline-block;width:13px;height:13px;border-radius:3px;margin-right:3px}}
.how{{margin:18px 0 0;padding:13px;background:#F9FAFB;border-radius:9px;
font-size:12.5px;color:#4B5563}}
.how code{{font:500 11.5px/1.5 ui-monospace,Menlo,monospace;display:block;
margin-top:5px;color:#111827}}
iframe{{flex:1;border:0;height:100vh;width:100%}}
@media (max-width:820px){{body{{flex-direction:column;height:auto;overflow:auto}}
.side{{width:auto;flex:none;border-right:0;border-bottom:1px solid #E5E7EB}}
iframe{{height:78vh}}}}
@media (prefers-color-scheme:dark){{
body{{background:#0D1117;color:#E6EDF3}}
.side{{border-color:#262C33}} .card{{border-color:#262C33}}
.card:hover{{border-color:#4B5563;background:#161B22}}
.lede,.meta p,.how{{color:#9BA7B4}} .meta code{{background:#161B22;color:#9BA7B4}}
.how{{background:#161B22}} .how code{{color:#E6EDF3}}}}
</style></head>
<body>
<div class="side">
<h1>Pick a template</h1>
<p class="lede">The same issue, rendered five ways. Click one to see it.</p>
{''.join(cards)}
<div class="how">Set your choice in <b>newsletter.toml</b>:
<code>[newsletter]<br>template = "digest"</code></div>
</div>
<iframe name="view" src="{e(current)}.html" title="preview"></iframe>
</body></html>"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--edition", default=None, help="default: the newest one")
    p.add_argument("--out", default=os.path.join(HERE, "build", "templates"))
    args = p.parse_args()

    path = args.edition
    if not path:
        found = sorted(glob.glob(os.path.join(HERE, "editions", "*.json")))
        if not found:
            print("no editions to preview", file=sys.stderr)
            return 1
        path = found[-1]

    with open(path, encoding="utf-8") as f:
        ed = json.load(f)

    cfg = _config.load()
    names = _config.template_names()
    current = cfg["newsletter"]["template"]
    if current not in names:
        current = names[0]

    os.makedirs(args.out, exist_ok=True)
    for n in names:
        with open(os.path.join(args.out, f"{n}.html"), "w", encoding="utf-8") as f:
            f.write(build_email.build(ed, cfg, template=n))
    index = os.path.join(args.out, "index.html")
    with open(index, "w", encoding="utf-8") as f:
        f.write(picker(names, cfg, current))

    print(f"{len(names)} template(s) from {os.path.basename(path)}")
    print(f"open {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
