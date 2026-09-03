#!/usr/bin/env python3
"""Fetch the top-voted Hacker News stories from the last N hours.

Zero dependencies (stdlib only). Outputs JSON on stdout so the newsletter
agent gets deterministic, real data instead of recalling it from memory.

Usage:
    python3 fetch_hn.py [--hours 48] [--limit 5] [--min-points 50]
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

ALGOLIA = "https://hn.algolia.com/api/v1/search"
UA = {"User-Agent": "daily-newsletter/1.0 (personal digest)"}


def get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(hours: int, limit: int, min_points: int):
    cutoff = int(time.time()) - hours * 3600
    params = urllib.parse.urlencode({
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff},points>{min_points}",
        "hitsPerPage": 60,
    })
    data = get(f"{ALGOLIA}?{params}")

    stories = []
    for h in data.get("hits", []):
        title = (h.get("title") or "").strip()
        if not title:
            continue
        oid = h.get("objectID")
        stories.append({
            "title": title,
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
            "hn_url": f"https://news.ycombinator.com/item?id={oid}",
            "points": h.get("points") or 0,
            "comments": h.get("num_comments") or 0,
            "author": h.get("author"),
            "created_at": h.get("created_at"),
            "is_self_post": not h.get("url"),
        })

    # Purely top-voted. Comment count is shown but never sways the ranking.
    stories.sort(key=lambda s: s["points"], reverse=True)
    return stories[:limit]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--min-points", type=int, default=50)
    a = p.parse_args()

    try:
        stories = fetch(a.hours, a.limit, a.min_points)
    except Exception as e:  # noqa: BLE001 - surface the reason, keep exit code
        print(json.dumps({"error": str(e), "stories": []}), file=sys.stdout)
        return 1

    if not stories:  # widen the net rather than send an empty section
        stories = fetch(a.hours * 2, a.limit, max(20, a.min_points // 2))

    print(json.dumps({"count": len(stories), "stories": stories}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
