#!/usr/bin/env python3
"""Render the daily newsletter HTML from a content JSON file.

The agent's job is to gather good content and write content.json.
This script's job is to make it look right, every single day, identically.
Keeping the two separate means the layout can't drift or get half-remembered.

Typography and colour live in a <style> block rather than in inline style
attributes. That is a deliberate trade: inline styles survive more email
clients, but repeating a 70-character font stack a hundred times pushed the
document past 55KB, and the whole thing has to be handed to the Gmail tool as
a single string every morning. Layout (padding, widths, borders) stays inline,
so even a client that drops <style> gets a correctly structured page.

Usage:
    python3 build_email.py content.json > edition.html
    python3 build_email.py content.json --raw    # skip minification
"""
import html
import json
import re
import sys
from datetime import datetime

# ---------------------------------------------------------------- palette ---
# Warm paper + ink, with muted jewel accents. One accent per section so the
# eye can find its place without anything shouting.
L = {"paper": "#FBF8F3", "card": "#FFFDFA", "ink": "#23272B",
     "soft": "#6E6A63", "faint": "#94908A", "rule": "#E6DED1"}
D = {"paper": "#15181B", "card": "#1C2025", "ink": "#E9E5DD",
     "soft": "#A39E95", "faint": "#7C776F", "rule": "#31363C"}

# (light, dark) pairs
ACCENTS = {
    "amber":  ("#A8792F", "#DCBA72"),
    "pine":   ("#2F6B62", "#77B8AE"),
    "indigo": ("#47527A", "#96A2CC"),
    "plum":   ("#77496B", "#C293B4"),
    "clay":   ("#AF5C36", "#E29268"),
    "moss":   ("#5A6B33", "#AFC17A"),
    "iris":   ("#5B4B8A", "#A99AD6"),
}

UP, DOWN = "#2F7A52", "#B04A3C"
UP_D, DOWN_D = "#7FBF9A", "#E08A7C"

SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,'Times New Roman',serif"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


# ------------------------------------------------------------- stylesheet ---

def stylesheet():
    acc_light = "\n".join(f".{k}{{color:{v[0]}}}.bg-{k}{{background:{v[0]}}}"
                          for k, v in ACCENTS.items())
    acc_dark = "\n".join(f".{k}{{color:{v[1]}!important}}"
                         f".bg-{k}{{background:{v[1]}!important}}"
                         for k, v in ACCENTS.items())
    return f"""
body{{margin:0;padding:0;background:{L['paper']};-webkit-font-smoothing:antialiased}}
a{{text-decoration:none}}
.w{{background:{L['paper']}}}
.ink,.ink a{{color:{L['ink']}}}
.soft{{color:{L['soft']}}}
.fnt{{color:{L['faint']}}}
.card{{background:{L['card']};border:1px solid {L['rule']}}}
.hr{{background:{L['ink']}}}
.hair{{background:{L['rule']}}}
.up{{color:{UP}}}
.dn{{color:{DOWN}}}
.chip{{border:1px solid {L['rule']};color:{L['soft']}}}
.cite{{border-bottom:1px solid {L['rule']}}}
.ttl{{font:400 36px/1.05 {SERIF};letter-spacing:.22em;text-transform:uppercase}}
.dat{{font:600 11px/1 {SANS};letter-spacing:.2em;text-transform:uppercase}}
.qm{{font:700 42px/.6 {SERIF};opacity:.55}}
.qt{{font:400 italic 21px/1.62 {SERIF}}}
.att{{font:600 13px/1.4 {SANS};letter-spacing:.05em}}
.note{{font:400 14px/1.6 {SANS}}}
.snum{{font:700 13px/1 {SANS};letter-spacing:.06em}}
.shd{{font:700 12px/1 {SANS};letter-spacing:.19em;text-transform:uppercase}}
.idx{{font:600 15px/1.4 {SERIF}}}
.h1{{font:600 18px/1.4 {SERIF}}}
.h2{{font:600 17px/1.42 {SERIF}}}
.sub{{font:400 italic 13px/1.45 {SERIF}}}
.meta{{font:400 12px/1 {SANS};letter-spacing:.04em}}
.bul{{font:700 15px/1.55 {SANS}}}
.txt{{font:400 15px/1.55 {SANS}}}
.bod{{font:400 15px/1.65 {SANS}}}
.lnk{{font:600 13px/1 {SANS};letter-spacing:.02em}}
.sep{{font:400 13px/1 {SANS}}}
.tag{{font:700 10px/1 {SANS};letter-spacing:.14em;text-transform:uppercase}}
.ilbl{{font:600 10px/1 {SANS};letter-spacing:.14em;text-transform:uppercase}}
.ival{{font:600 19px/1.2 {SERIF}}}
.idl{{font:600 13px/1.3 {SANS}}}
.cptn{{font:400 12px/1.7 {SANS}}}
.chipf{{font:600 10px/1 {SANS};letter-spacing:.1em;text-transform:uppercase}}
.inum{{font:400 22px/1 {SERIF}}}
.itxt{{font:400 15px/1.5 {SANS}}}
.iwhy{{font:400 italic 13px/1.5 {SERIF}}}
.iprom{{font:600 italic 16px/1.45 {SERIF}}}
{acc_light}
@media (prefers-color-scheme:dark){{
body,.w{{background:{D['paper']}!important}}
.ink,.ink a{{color:{D['ink']}!important}}
.soft{{color:{D['soft']}!important}}
.fnt{{color:{D['faint']}!important}}
.card{{background:{D['card']}!important;border-color:{D['rule']}!important}}
.hr{{background:{D['ink']}!important}}
.hair{{background:{D['rule']}!important}}
.up{{color:{UP_D}!important}}
.dn{{color:{DOWN_D}!important}}
.chip{{border-color:{D['rule']}!important;color:{D['soft']}!important}}
.cite{{border-bottom-color:{D['rule']}!important}}
{acc_dark}
}}
@media only screen and (max-width:620px){{
.pad{{padding-left:22px!important;padding-right:22px!important}}
.ttl{{font-size:30px!important;letter-spacing:.16em!important}}
}}
"""


# --------------------------------------------------------------- fragments ---

def bullets(items, accent):
    """Key points. Custom bullet glyph in the section accent colour."""
    if not items:
        return ""
    rows = "".join(
        f'<tr><td class="bul {accent}" style="width:14px;vertical-align:top;'
        f'padding:0 0 7px 0">&bull;</td>'
        f'<td class="txt soft" style="padding:0 0 7px 0">{e(b)}</td></tr>'
        for b in items)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
            f' style="width:100%;margin:9px 0 0 0">{rows}</table>')


def links(pairs, accent):
    """`Read -> . Discuss ->` trailing links."""
    parts = [f'<a href="{e(u)}" class="lnk {accent}">{e(lbl)} &rarr;</a>'
             for lbl, u in pairs if u]
    if not parts:
        return ""
    sep = '<span class="sep fnt"> &nbsp;&middot;&nbsp; </span>'
    return f'<div style="padding:11px 0 0 0">{sep.join(parts)}</div>'


def section_head(num, title, accent):
    """`01 | HACKER NEWS` -- a numbered rule, newspaper-department style."""
    return f"""<tr><td style="padding:34px 0 0 0">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%"><tr>
<td class="snum {accent}" style="width:34px;padding:0 0 9px 0">{num:02d}</td>
<td class="shd ink" style="padding:0 0 9px 0">{e(title)}</td>
</tr></table>
<div class="bg-{accent}" style="height:2px;font-size:0;line-height:0">&nbsp;</div>
</td></tr>"""


def headline(item, key, cls="h2"):
    t = e(item.get(key))
    u = item.get("url")
    return f'<a href="{e(u)}" class="{cls} ink">{t}</a>' if u else \
           f'<span class="{cls} ink">{t}</span>'


# ---------------------------------------------------------------- sections ---

def render_quote(q):
    author = e(q.get("author", "Unknown"))
    if q.get("source_url"):
        author = f'<a href="{e(q["source_url"])}" class="ink cite">{author}</a>'
    work = (f'<span class="fnt" style="font-style:italic">, {e(q["work"])}</span>'
            if q.get("work") else "")
    note = (f'<p class="note soft" style="margin:16px 0 0 0">{e(q["note"])}</p>'
            if q.get("note") else "")
    return f"""<tr><td style="padding:36px 0 4px 0">
<div class="card" style="border-left:3px solid {ACCENTS['amber'][0]};padding:28px 30px 26px 30px">
<div class="qm amber" style="padding:0 0 6px 0">&ldquo;</div>
<p class="qt ink" style="margin:0">{e(q.get('text', ''))}</p>
<p class="att soft" style="margin:18px 0 0 0">&mdash;&nbsp;{author}{work}</p>
{note}</div></td></tr>"""


def render_hn(stories, accent):
    out = []
    for i, s in enumerate(stories, 1):
        out.append(f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%"><tr>
<td class="idx fnt" style="width:30px;vertical-align:top;padding:22px 0 0 0">{i}.</td>
<td style="padding:22px 0 0 0">{headline(s, 'title', 'h1')}
<div class="meta fnt" style="padding:6px 0 0 0">{s.get('points', 0)} points &nbsp;&middot;&nbsp; {s.get('comments', 0)} comments</div>
{bullets(s.get('bullets'), accent)}
{links([('Read', s.get('url')), ('Discuss', s.get('hn_url'))], accent)}
</td></tr></table>""")
    return f'<tr><td style="padding:0 0 6px 0">{"".join(out)}</td></tr>'


def render_markets(m, accent):
    parts = []
    idx = m.get("indices") or []
    if idx:
        cells = []
        for x in idx:
            d = (x.get("direction") or "flat").lower()
            cls = "up" if d == "up" else "dn" if d == "down" else "soft"
            arrow = "&#9650;" if d == "up" else "&#9660;" if d == "down" else "&ndash;"
            val = (x.get("value") or "").strip()
            # index rows carry a level; sector rows are change-only
            has_val = val and val != "—"
            val_html = f'<div class="ival ink" style="padding:6px 0 0 0">{e(val)}</div>' if has_val else ""
            cells.append(
                f'<td style="padding:14px 16px 14px 0;vertical-align:top">'
                f'<div class="ilbl fnt">{e(x.get("name"))}</div>{val_html}'
                f'<div class="idl {cls}" style="padding:{3 if has_val else 6}px 0 0 0">'
                f'{arrow}&nbsp;{e(x.get("change"))}</div></td>')
        # two per row keeps it readable on a phone
        rows = "".join("<tr>" + "".join(cells[i:i + 2]) + "</tr>"
                       for i in range(0, len(cells), 2))
        parts.append(
            f'<div class="card" style="padding:4px 18px;margin:20px 0 0 0">'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
            f' style="width:100%">{rows}</table></div>')

    for st in m.get("stories") or []:
        parts.append(f'<div style="padding:22px 0 0 0">{headline(st, "headline")}'
                     f'{bullets(st.get("bullets"), accent)}'
                     f'{links([(st.get("source") or "Source", st.get("url"))], accent)}</div>')
    return f'<tr><td style="padding:0 0 6px 0">{"".join(parts)}</td></tr>'


def render_stories(items, accent, key="headline"):
    out = []
    for it in items:
        tag = (f'<div class="tag {accent}" style="padding:0 0 7px 0">{e(it["tag"])}</div>'
               if it.get("tag") else "")
        sub = (f'<div class="sub fnt" style="padding:5px 0 0 0">{e(it["subtitle"])}</div>'
               if it.get("subtitle") else "")
        out.append(f'<div style="padding:22px 0 0 0">{tag}{headline(it, key)}{sub}'
                   f'{bullets(it.get("bullets"), accent)}'
                   f'{links([(it.get("link_label") or "Read", it.get("url"))], accent)}</div>')
    return f'<tr><td style="padding:0 0 6px 0">{"".join(out)}</td></tr>'


def render_learn(x, accent):
    chips = "".join(
        f'<span class="chip chipf" style="display:inline-block;padding:4px 9px;'
        f'margin:0 6px 0 0">{e(t)}</span>' for t in x.get("tags") or [])
    chips = f'<div style="padding:16px 0 0 0">{chips}</div>' if chips else ""
    body = "".join(f'<p class="bod soft" style="margin:0 0 11px 0">{e(p)}</p>'
                   for p in x.get("body", []))
    return f"""<tr><td style="padding:0 0 6px 0">
<div class="card" style="border-left:3px solid {ACCENTS[accent][0]};padding:24px 26px 22px 26px;margin:22px 0 0 0">
<div class="h1 ink" style="padding:0 0 12px 0">{e(x.get('title'))}</div>
{body}{chips}</div></td></tr>"""


def render_ideas(x, accent):
    """The Altucher drill: ten ideas against one prompt, every morning.

    The numerals carry the section accent and the gloss sits in italics
    underneath, so ten items still scan as a list rather than a wall.
    """
    prompt = (f'<div class="iprom {accent}" style="padding:20px 0 4px 0">'
              f'{e(x["prompt"])}</div>') if x.get("prompt") else ""
    note = (f'<div class="sub fnt" style="padding:4px 0 0 0">{e(x["note"])}</div>'
            if x.get("note") else "")

    rows = []
    for i, it in enumerate(x.get("items") or [], 1):
        # accept either a bare string or {text, why}
        text, why = (it, None) if isinstance(it, str) else (it.get("text"), it.get("why"))
        why_html = (f'<div class="iwhy fnt" style="padding:4px 0 0 0">{e(why)}</div>'
                    if why else "")
        rows.append(
            f'<tr><td class="inum {accent}" style="width:34px;vertical-align:top;'
            f'padding:14px 8px 0 0;text-align:right">{i}</td>'
            f'<td style="padding:14px 0 0 0">'
            f'<div class="itxt ink">{e(text)}</div>{why_html}</td></tr>')

    return (f'<tr><td style="padding:0 0 6px 0">{prompt}{note}'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"'
            f' style="width:100%">{"".join(rows)}</table></td></tr>')


# ------------------------------------------------------------------- shell ---

PLAN = [
    ("hn",       "Hacker News · Last 24 Hours", "pine",   render_hn),
    ("markets",  "Markets · India & World", "indigo", render_markets),
    ("trends",   "Trends & Signals",             "moss",   render_stories),
    ("research", "From the Research Desk",           "plum",
     lambda v, a: render_stories(v, a, "title")),
    ("wild",     "Wonderfully Odd Ideas",            "amber",  render_stories),
    ("learn",    "One Thing to Learn",               "clay",   render_learn),
    ("ideas",    "Ten Ideas",                        "iris",   render_ideas),
]


def build(c):
    date_line = c.get("date_line") or datetime.now().strftime("%A, %d %B %Y")
    rows, n = [], 0

    if c.get("quote"):
        rows.append(render_quote(c["quote"]))

    for key, title, accent, fn in PLAN:
        val = c.get(key)
        if not val:
            continue
        n += 1
        rows.append(section_head(n, title, accent))
        rows.append(fn(val, accent))

    issue = (f'<span class="fnt"> &nbsp;&middot;&nbsp; No. {e(c["issue"])}</span>'
             if c.get("issue") else "")
    preheader = c.get("preheader") or (
        "Your daily brief: a quote, the best of Hacker News, markets, "
        "and a little something new.")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>The Morning &mdash; {e(date_line)}</title>
<style>{stylesheet()}</style>
</head>
<body>
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(preheader)}</div>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" class="w" style="width:100%">
<tr><td align="center" style="padding:34px 12px 48px 12px">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:620px">

<tr><td class="pad" style="padding:0 34px">
<div class="hr" style="height:3px;font-size:0;line-height:0">&nbsp;</div>
<div style="text-align:center;padding:26px 0 0 0">
<div class="ttl ink">The&nbsp;Morning</div>
<div style="padding:16px 0 0 0"><span class="dat fnt">{e(date_line)}</span>{issue}</div>
</div>
<div class="hair" style="height:1px;margin:24px 0 0 0;font-size:0;line-height:0">&nbsp;</div>
</td></tr>

<tr><td class="pad" style="padding:0 34px">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%">
{''.join(rows)}
</table>
</td></tr>

<tr><td class="pad" style="padding:44px 34px 0 34px">
<div class="hair" style="height:1px;font-size:0;line-height:0">&nbsp;</div>
<p class="cptn fnt" style="margin:18px 0 0 0;text-align:center">
Assembled each morning from Hacker News, Goodreads and the day&rsquo;s reporting.<br>
Sources are linked throughout &mdash; read the originals before you act on any of it.
</p>
</td></tr>

</table>
</td></tr></table>
</body></html>"""


def minify(h):
    """Whitespace only.

    Nothing here may touch ":" or ";", which appear in visible copy as often
    as they do in CSS.
    """
    h = re.sub(r"<!--.*?-->", "", h, flags=re.S)
    h = re.sub(r"\n\s*", " ", h)
    h = re.sub(r" {2,}", " ", h)
    return h.strip()


def main():
    if len(sys.argv) < 2:
        print("usage: build_email.py content.json > edition.html", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        content = json.load(f)
    out = build(content)
    if "--raw" not in sys.argv:
        out = minify(out)
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
