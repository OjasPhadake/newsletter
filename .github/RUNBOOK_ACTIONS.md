# The Morning — GitHub Actions runbook

You are building and sending today's edition of *The Morning*, a personal
newsletter for Ojas — a chemical engineering / data science student at IIT
Madras. You are running headless in GitHub Actions. Nobody is watching, so
never stop to ask for confirmation: make the call and keep going.

The working directory is the repository root. `PROMPT.md` holds the editorial
briefs — **read it first**, it is the source of truth for the quote brief, the
ten-ideas brief, the accuracy rules and the voice. This file only covers what
is *different* about running here.

## What is different in Actions

There are no MCP connectors on this runner. In particular:

- **No Gmail tool.** Send with `scripts/send_email.py` over SMTP instead.
- **No alphaXiv tool.** Use `scripts/fetch_papers.py` for the research section.
- **Full internet access.** WebFetch works on any domain, so the rule about
  reading each article before summarising it applies with no excuses.

## Step 1 — memory

```bash
python3 scripts/history.py show
```

`state/history.json` is committed to this repository and pushed after every
send, so it is authoritative and complete. Nothing may ever repeat: no quote,
no idea, no ideas prompt, no Hacker News story, no link.

## Step 2 — gather

```bash
python3 scripts/fetch_hn.py                    > /tmp/hn.json      # 48h, top 5 by votes
python3 scripts/fetch_papers.py --days 30 --sector academia > /tmp/papers.json
python3 scripts/fetch_labs.py   --days 30      > /tmp/labs.json
python3 scripts/fetch_ideas.py                 > /tmp/ideas.json
```

Then follow the table in `PROMPT.md`. Specifically:

- **Hacker News:** take the five stories `fetch_hn.py` returns, in its order.
  They are the top-voted of the last 48 hours; do not re-rank them. WebFetch
  each URL and write the bullets from what the article actually says.
- **Markets:** WebSearch plus WebFetch for the most recent Indian close.
  Exact Sensex and Nifty levels with point *and* percentage change, sector
  indices, USD/INR, FII/DII flows, each from a named source you link.
- **Quote:** fetch a Goodreads tag page and quote verbatim. Re-read the quote
  brief — an ordinary motivational quote is a failure, not a near miss.
- **Research:** exactly two items — one industry, one academic. The industry
  one comes from `/tmp/labs.json` (lab blogs, provenance certain); the academic
  one from `/tmp/papers.json` `verified`. Anything from `trending` is a
  tie-breaker only and needs its arXiv page fetched to confirm the lab.
- **Ten Ideas:** a fresh, plainly-worded prompt every day, never one used in
  the last 120 days. Ground them in `/tmp/ideas.json`; if Reddit rate-limited
  the script, WebFetch the subreddit RSS feeds directly.

If a figure cannot be verified, leave it out. Do not approximate.

## Step 3 — build and check

```bash
python3 scripts/history.py check editions/<TODAY>.json    # MUST exit 0
python3 scripts/build_email.py editions/<TODAY>.json > build/edition.html
```

If `check` fails, replace the offending items and run it again. Never edit
`history.py` to make it pass. Never send an edition that has not passed.

## Step 4 — send

Write a short plain-text fallback to `build/edition.txt` (masthead, quote, the
HN headlines with links, the market line, the section names). Then:

```bash
python3 scripts/send_email.py \
  --html build/edition.html \
  --text-file build/edition.txt \
  --subject "The Morning · <Day D Mon> — <the three most interesting things>" \
  --to "$RECIPIENT" \
  <extra flags given to you, e.g. --dry-run>
```

`GMAIL_USER` and `GMAIL_APP_PASSWORD` are already in the environment. Never
print them, never write them to a file, never include them in your summary.

If you were given `--dry-run`, pass it through and do not record history.

## Step 5 — record

```bash
python3 scripts/history.py record editions/<TODAY>.json
```

The workflow commits and pushes `editions/` and `state/` for you. Do not push
yourself.

## Finish

End your final message with a short report: the quote and its author, the five
HN headlines, the market line, the ideas prompt, and whether the send
succeeded. If anything was omitted for lack of verification, say what and why.

## If today's edition file already exists

`editions/<TODAY>.json` may already be present if an issue went out earlier
today. Do not overwrite it. Write `editions/<TODAY>-2.json` instead (then
`-3`, and so on), and set `"issue"` to the next number. `history.py` reads the
date from the filename prefix and keys records on (date, issue), so both
issues stay on record and neither one's quote or ideas can come back.
