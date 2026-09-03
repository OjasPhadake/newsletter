#!/usr/bin/env python3
"""Gather raw material for the Ten Ideas section.

The section is not a digest of these — the agent writes the ideas itself. This
just puts real wants in front of it, so the ideas are grounded in things people
actually asked for rather than invented in a vacuum.

Reddit's JSON API returns 403 to unauthenticated clients, but the Atom feeds
are still open, so the subreddits come in as RSS.

    python3 fetch_ideas.py --limit 12
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; daily-newsletter/1.0; "
                    "+https://github.com/OjasPhadake/newsletter)"}

# Subreddits where people post things they wish existed.
SUBS = [
    "SomebodyMakeThis", "Lightbulb", "AppIdeas",
    "Business_Ideas", "crazyideas", "InternetIsBeautiful",
]
ALGOLIA = "https://hn.algolia.com/api/v1/search"


def fetch(url, timeout=20, retries=2):
    """Reddit rate-limits bursts, so back off and try again rather than
    dropping a whole subreddit on the first 429."""
    delay = 4.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def clean(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def from_reddit(sub, per_sub):
    xml = fetch(f"https://www.reddit.com/r/{sub}/top/.rss?t=week")
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S)[:per_sub]:
        title = re.search(r"<title>(.*?)</title>", entry, re.S)
        link = re.search(r'<link[^>]*href="([^"]+)"', entry)
        if not title:
            continue
        out.append({"source": f"r/{sub}", "title": clean(title.group(1)),
                    "url": link.group(1) if link else None})
    return out


def from_hn(per_query):
    """Long-lived 'Ask HN' threads about things that ought to exist."""
    queries = [
        "Ask HN what should exist",
        "Ask HN what doesn't exist that should",
        "Ask HN side project ideas",
        "Ask HN what would you build",
    ]
    out = []
    for q in queries:
        url = f"{ALGOLIA}?" + urllib.parse.urlencode(
            {"query": q, "tags": "story", "hitsPerPage": per_query})
        try:
            hits = json.loads(fetch(url)).get("hits", [])
        except Exception:  # noqa: BLE001
            continue
        # Algolia matches loosely. Require an idea-shaped *phrase*, or
        # "what should I know about CSS grid" sails through on the word
        # "should".
        wanted = ("should exist", "doesn't exist", "does not exist",
                  "what should i build", "what would you build",
                  "side project", "startup idea", "project ideas",
                  "business idea", "app ideas", "what to build",
                  "ideas that", "wish existed", "someone should")
        for h in hits:
            if (h.get("points") or 0) < 20:
                continue
            if not any(w in (h.get("title") or "").lower() for w in wanted):
                continue
            out.append({
                "source": "Hacker News",
                "title": clean(h.get("title")),
                "url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                "points": h.get("points"),
                "comments": h.get("num_comments"),
            })
    seen, unique = set(), []
    for h in sorted(out, key=lambda x: x.get("points", 0), reverse=True):
        if h["url"] in seen:
            continue
        seen.add(h["url"])
        unique.append(h)
    return unique


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10, help="items per subreddit")
    a = p.parse_args()

    result = {"reddit": [], "hacker_news": [], "browse": [
        # Worth the agent fetching directly when it wants a curated list.
        {"name": "Y Combinator — Requests for Startups",
         "url": "https://www.ycombinator.com/rfs"},
    ], "errors": []}

    consecutive_429 = 0
    for n, sub in enumerate(SUBS):
        if n:
            time.sleep(3.0)   # Reddit 429s on bursts; pace the feeds
        try:
            result["reddit"].extend(from_reddit(sub, a.limit))
        except Exception as exc:  # noqa: BLE001 - a dead sub shouldn't stop the rest
            result["errors"].append(f"r/{sub}: {exc}")
            if "429" in str(exc):
                consecutive_429 += 1
                if consecutive_429 >= 2:
                    result["errors"].append(
                        "reddit rate-limiting this client; skipping remaining subreddits")
                    break
            else:
                consecutive_429 = 0

    try:
        result["hacker_news"] = from_hn(8)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"hn: {exc}")

    result["counts"] = {k: len(result[k]) for k in ("reddit", "hacker_news")}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if any(result["counts"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
