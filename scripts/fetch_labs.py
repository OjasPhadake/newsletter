#!/usr/bin/env python3
"""Recent research posts straight from the labs' own blogs.

This exists because affiliation lookup does not work for industry labs.
OpenAlex resolves only ~22 OpenAI and ~88 DeepMind arXiv papers per year —
a small fraction of what they actually publish — because arXiv metadata
carries no affiliation and OpenAlex can only infer it later from a published
version. University output resolves far better than company output.

A lab's own blog sidesteps the problem entirely: if a post is on
anthropic.com/research, it is Anthropic's, and no inference is required.
Most labs publish Atom or RSS; the two that don't are scraped from HTML.

    python3 fetch_labs.py --days 30
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; daily-newsletter/1.0; "
                    "+https://github.com/OjasPhadake/newsletter)"}

# Note: OpenAI's feed is general news, not a research feed — it mixes papers
# with customer stories and product launches. The caller must filter.
FEEDS = [
    ("OpenAI",             "https://openai.com/news/rss.xml"),
    ("Google DeepMind",    "https://deepmind.google/blog/rss.xml"),
    ("Google Research",    "https://research.google/blog/rss/"),
    ("Microsoft Research", "https://www.microsoft.com/en-us/research/feed/"),
    ("Meta (FAIR)",        "https://research.facebook.com/feed/"),
    ("Berkeley BAIR",      "https://bair.berkeley.edu/blog/feed.xml"),  # slow; often times out
    ("MIT News — AI",      "https://news.mit.edu/rss/topic/artificial-intelligence2"),
    ("CMU MLD",            "https://blog.ml.cmu.edu/feed/"),
]

# No feed of any kind; the index page is the only option.
SCRAPE = [
    ("Anthropic", "https://www.anthropic.com/research", r"/research/([a-z0-9-]{8,})"),
    ("Anthropic", "https://www.anthropic.com/news",     r"/news/([a-z0-9-]{8,})"),
]

DATE_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
)


def get(url, timeout=35, retries=2):
    delay = 3.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def clean(s):
    s = s or ""
    # Unwrap CDATA first: "<![CDATA[Title]]>" contains no '>' until the
    # terminator, so the tag-stripper below would otherwise swallow it whole.
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def parse_date(raw):
    raw = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(raw, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def tag(block, *names):
    for n in names:
        m = re.search(rf"<{n}[^>]*>(.*?)</{n}>", block, re.S)
        if m:
            return m.group(1)
    return ""


def from_feed(lab, url, cutoff, per_lab):
    xml = get(url)
    out = []
    # RSS uses <item>, Atom uses <entry>.
    for block in re.findall(r"<(?:item|entry)[ >](.*?)</(?:item|entry)>", xml, re.S):
        title = clean(tag(block, "title"))
        if not title:
            continue
        link = clean(tag(block, "link"))
        if not link or not link.startswith("http"):
            m = re.search(r'<link[^>]*href="([^"]+)"', block)
            link = m.group(1) if m else None
        when = parse_date(clean(tag(block, "pubDate", "published", "updated", "dc:date")))
        if when and when < cutoff:
            continue
        out.append({
            "lab": lab, "title": title, "url": link,
            "published": when.date().isoformat() if when else None,
            "summary": clean(tag(block, "description", "summary", "content"))[:500],
        })
        if len(out) >= per_lab:
            break
    return out


def from_scrape(lab, url, pattern, per_lab):
    """No feed available — recover post slugs from the index page.

    There are no dates here, so the caller must check recency on the page
    itself before using anything from this source.
    """
    page = get(url)
    base = re.match(r"(https://[^/]+)", url).group(1)
    seen, out = set(), []
    for slug in re.findall(pattern, page):
        if slug in seen:
            continue
        seen.add(slug)
        path = url[len(base):].rstrip("/")
        out.append({
            "lab": lab,
            "title": slug.replace("-", " ").capitalize(),
            "url": f"{base}{path}/{slug}",
            "published": None,
            "title_is_slug": True,     # derived from the URL, not the page
            "needs_date_check": True,  # no date here; confirm on the page
        })
        if len(out) >= per_lab:
            break
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--per-lab", type=int, default=6)
    a = p.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days)
    result = {"window_days": a.days, "posts": [], "errors": []}

    for lab, url in FEEDS:
        try:
            result["posts"].extend(from_feed(lab, url, cutoff, a.per_lab))
        except Exception as exc:  # noqa: BLE001 - one dead feed must not stop the rest
            result["errors"].append(f"{lab}: {exc}")
        time.sleep(0.5)

    for lab, url, pattern in SCRAPE:
        try:
            result["posts"].extend(from_scrape(lab, url, pattern, a.per_lab))
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"{lab} ({url}): {exc}")
        time.sleep(0.5)

    by_lab = {}
    for post in result["posts"]:
        by_lab[post["lab"]] = by_lab.get(post["lab"], 0) + 1
    result["counts"] = {"total": len(result["posts"]), "by_lab": by_lab}

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["posts"] else 1


if __name__ == "__main__":
    sys.exit(main())
