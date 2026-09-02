#!/usr/bin/env python3
"""Fetch recent papers from the arXiv API.

Replaces the alphaXiv MCP connector, which only exists inside a Claude
session. A GitHub Actions runner has neither, so the research section comes
straight from arXiv's public Atom API instead. Stdlib only, no key needed.

    python3 fetch_arxiv.py --categories cs.LG cs.AI --days 3 --limit 12
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://export.arxiv.org/api/query"
UA = {"User-Agent": "daily-newsletter/1.0 (personal digest; contact via github.com/OjasPhadake)"}


def tag(entry, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", entry, re.S)
    return " ".join(m.group(1).split()) if m else ""


def fetch(categories, limit):
    query = " OR ".join(f"cat:{c}" for c in categories)
    url = f"{API}?" + urllib.parse.urlencode({
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        # over-fetch, because the date filter trims the tail
        "max_results": max(limit * 4, 40),
    })
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(xml, days, limit):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        published = tag(entry, "published")
        try:
            when = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
        except ValueError:
            continue
        if when < cutoff:
            continue

        abs_url = tag(entry, "id")
        arxiv_id = abs_url.rsplit("/", 1)[-1]
        authors = re.findall(r"<author>\s*<name>(.*?)</name>", entry, re.S)
        summary = tag(entry, "summary")

        out.append({
            "arxiv_id": arxiv_id,
            "title": tag(entry, "title"),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "authors": [" ".join(a.split()) for a in authors[:4]],
            "published": published,
            "primary_category": (re.search(r'<arxiv:primary_category[^>]*term="([^"]+)"',
                                           entry) or [None, ""])[1]
            if re.search(r'<arxiv:primary_category[^>]*term="([^"]+)"', entry) else "",
            "summary": summary,
        })
        if len(out) >= limit:
            break
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--categories", nargs="+",
                   default=["cs.LG", "cs.AI", "cs.CL", "stat.ML"])
    p.add_argument("--days", type=int, default=3)
    p.add_argument("--limit", type=int, default=12)
    a = p.parse_args()

    try:
        papers = parse(fetch(a.categories, a.limit), a.days, a.limit)
    except Exception as exc:  # noqa: BLE001 - report, don't crash the run
        print(json.dumps({"error": str(exc), "papers": []}))
        return 1

    if not papers:  # quiet weekend on arXiv; widen rather than print nothing
        papers = parse(fetch(a.categories, a.limit), a.days + 4, a.limit)

    print(json.dumps({"count": len(papers), "papers": papers}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
