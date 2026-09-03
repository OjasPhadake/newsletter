#!/usr/bin/env python3
"""Find recent AI / ML / control papers from top labs and universities.

Affiliation is the hard part: arXiv's own API does not expose it, so a plain
category listing cannot tell a Stanford paper from anyone else's. This pulls
from two complementary sources and labels which is which:

  openalex  arXiv preprints whose author affiliations OpenAlex has actually
            resolved to one of the institutions below. Affiliation is
            *verified*, but OpenAlex indexes arXiv with a lag of a week or
            two, so the freshest work is missing.
  hf        Hugging Face's daily papers list. Fresh and community-curated,
            but carries no affiliation data — the caller must verify.

Neither source covers Anthropic, which barely appears in OpenAlex at all
(works_count 0 at time of writing). Those have to be found by search.

    python3 fetch_papers.py --days 30 --limit 20
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

OPENALEX = "https://api.openalex.org/works"
HF_DAILY = "https://huggingface.co/api/daily_papers"
ARXIV_SOURCE = "S4306400194"          # arXiv (Cornell University)
MAILTO = "ch22b007@smail.iitm.ac.in"  # OpenAlex asks for this; it buys a faster pool
UA = {"User-Agent": f"daily-newsletter/1.0 (mailto:{MAILTO})"}

# Frontier labs and the universities that publish alongside them.
INSTITUTIONS = {
    "I4210161460": "OpenAI",
    "I4210090411": "Google DeepMind",
    "I1291425158": "Google",
    "I4210114444": "Meta",
    "I4210164937": "Microsoft Research",
    "I4210156221": "Allen Institute for AI",
    "I63966007":   "MIT",
    "I97018004":   "Stanford",
    "I95457486":   "UC Berkeley",
    "I74973139":   "CMU",
    "I20089843":   "Princeton",
    "I136199984":  "Harvard",
    "I122411786":  "Caltech",
    "I201448701":  "U. Washington",
    "I205783295":  "Cornell",
    "I57206974":   "NYU",
    "I157725225":  "UIUC",
    "I130701444":  "Georgia Tech",
    "I78577930":   "Columbia",
    "I27837315":   "U. Michigan",
    "I40120149":   "Oxford",
    "I241749":     "Cambridge",
    "I35440088":   "ETH Zurich",
    "I5124864":    "EPFL",
    "I185261750":  "U. Toronto",
    "I4210164802": "Mila",
}

# Topic net: LLMs and ML, plus control theory, which the reader asked for by name.
TERMS = ("language model OR LLM OR transformer OR reinforcement learning OR "
         "neural network OR machine learning OR agent OR alignment OR "
         "control theory OR optimal control OR reasoning OR diffusion model")


def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def from_openalex(days, limit):
    since = (date.today() - timedelta(days=days)).isoformat()
    flt = ",".join([
        f"from_publication_date:{since}",
        "authorships.institutions.lineage:" + "|".join(INSTITUTIONS),
        f"primary_location.source.id:{ARXIV_SOURCE}",
        "title_and_abstract.search:" + TERMS,
    ])
    url = f"{OPENALEX}?" + urllib.parse.urlencode({
        "filter": flt, "sort": "publication_date:desc",
        "per-page": min(limit * 3, 100), "mailto": MAILTO})

    out = []
    for w in get(url).get("results", []):
        insts, matched = set(), set()
        for a in w.get("authorships", []):
            for i in a.get("institutions", []):
                insts.add(i.get("display_name"))
                for lin in i.get("lineage", []):
                    key = lin.rsplit("/", 1)[-1]
                    if key in INSTITUTIONS:
                        matched.add(INSTITUTIONS[key])
        doi = (w.get("ids") or {}).get("doi") or ""
        arxiv_id = doi.split("arxiv.")[-1] if "arxiv." in doi else None
        out.append({
            "source": "openalex",
            "affiliation_verified": True,
            "title": " ".join((w.get("title") or "").split()),
            "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                   else (w.get("primary_location") or {}).get("landing_page_url"),
            "arxiv_id": arxiv_id,
            "published": w.get("publication_date"),
            "top_labs": sorted(matched),
            "all_institutions": sorted(x for x in insts if x)[:6],
            "authors": [a.get("author", {}).get("display_name")
                        for a in w.get("authorships", [])[:5]],
            "cited_by": w.get("cited_by_count", 0),
        })
        if len(out) >= limit:
            break
    return out


def from_hugging_face(days, limit):
    """Community-curated dailies. Fresh, but affiliation must be checked."""
    out, seen = [], set()
    for back in range(0, min(days, 10)):
        day = (date.today() - timedelta(days=back)).isoformat()
        try:
            items = get(f"{HF_DAILY}?date={day}&limit=25", timeout=25)
        except Exception:  # noqa: BLE001 - one bad day shouldn't kill the run
            continue
        for it in items if isinstance(items, list) else []:
            p = it.get("paper") or {}
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            out.append({
                "source": "huggingface",
                "affiliation_verified": False,
                "title": " ".join((p.get("title") or "").split()),
                "url": f"https://arxiv.org/abs/{pid}",
                "arxiv_id": pid,
                "published": (p.get("publishedAt") or day)[:10],
                "upvotes": it.get("upvotes") or 0,
                "authors": [a.get("name") for a in (p.get("authors") or [])[:5]],
                "summary": " ".join((p.get("summary") or "").split())[:600],
            })
        if len(out) >= limit * 2:
            break
    out.sort(key=lambda x: (x.get("upvotes") or 0), reverse=True)
    return out[:limit]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--limit", type=int, default=15)
    a = p.parse_args()

    result = {"generated_at": datetime.now().isoformat(timespec="seconds"),
              "window_days": a.days, "errors": []}
    try:
        result["verified"] = from_openalex(a.days, a.limit)
    except Exception as exc:  # noqa: BLE001
        result["verified"], _ = [], result["errors"].append(f"openalex: {exc}")
    try:
        result["trending"] = from_hugging_face(a.days, a.limit)
    except Exception as exc:  # noqa: BLE001
        result["trending"], _ = [], result["errors"].append(f"huggingface: {exc}")

    result["counts"] = {"verified": len(result.get("verified", [])),
                        "trending": len(result.get("trending", []))}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if (result["counts"]["verified"] or result["counts"]["trending"]) else 1


if __name__ == "__main__":
    sys.exit(main())
