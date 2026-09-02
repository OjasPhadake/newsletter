# The Morning

A daily newsletter, assembled each morning and emailed at 07:00 IST.

Sections: a quote (Goodreads), the best of Hacker News from the last 24 hours
with real summaries, Indian and world markets, trends and signals, new AI
research, a few wonderfully odd things companies have done, and one concept
explained in three paragraphs.

## How it works

Content and presentation are separate on purpose.

```
PROMPT.md            what the scheduled agent does each morning
scripts/fetch_hn.py  pulls top HN stories from the last N hours (stdlib only)
scripts/build_email.py  turns an edition JSON into the email HTML
editions/*.json      one file per issue — the content, as data
state/history.json   what has been sent, so the newsletter doesn't repeat itself
```

The agent's job is judgement: pick the stories, read them, write the bullets.
The renderer's job is that the result looks the same every single day.

## Building an issue by hand

```bash
python3 scripts/fetch_hn.py --hours 24 --limit 6
python3 scripts/build_email.py editions/2026-09-03.json > /tmp/edition.html
python3 scripts/build_email.py editions/2026-09-03.json --raw   # readable output
```

Open the HTML in a browser to preview. It is theme-aware — the palette switches
with `prefers-color-scheme`.

## Design

Editorial: serif masthead, numbered section rules, warm paper ground
(`#FBF8F3`) against ink (`#23272B`). Each section owns one muted accent —
pine, indigo, moss, plum, amber, clay — so the eye can find its place without
anything shouting. Typography lives in a `<style>` block; layout stays inline,
so a client that strips `<style>` still gets a correctly structured page.

## Schedule

Runs as a Claude Code scheduled agent (`/schedule`). To change the time or
stop it, use that command.

## Uniqueness

Nothing repeats. `scripts/history.py` records every quote, idea, idea prompt,
HN story and link that has been sent, and `check` hard-fails the daily run if
today's edition collides with anything in `state/history.json`. Quotes and
ideas are barred forever; authors for 90 days, idea prompts for 120, links 45.

```bash
python3 scripts/history.py show
python3 scripts/history.py check editions/2026-09-04.json
python3 scripts/history.py record editions/2026-09-04.json --message-id <id>
```

The daily agent commits `state/history.json` back to this repo after each
send, which is how tomorrow's run knows what yesterday used.

## Automation

The daily send runs in GitHub Actions (`.github/workflows/daily.yml`) at
01:30 UTC = 07:00 IST, so it lands whether or not any machine of yours is on.
The runner follows `.github/RUNBOOK_ACTIONS.md`, which defers to `PROMPT.md`
for all editorial judgement.

Actions runners have no MCP connectors, so two things differ from running this
by hand in a Claude session:

| | Claude session | GitHub Actions |
|---|---|---|
| Sending | Gmail connector | `scripts/send_email.py` over SMTP |
| Research | alphaXiv connector | `scripts/fetch_arxiv.py` (arXiv Atom API) |

### Required repository secrets

| Secret | What it is |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | From `claude setup-token` — runs on your Claude subscription, no API billing |
| `GMAIL_USER` | The Gmail address that sends the newsletter |
| `GMAIL_APP_PASSWORD` | A Google [app password](https://myaccount.google.com/apppasswords) (needs 2-Step Verification) |

Optionally set a repository *variable* `RECIPIENT` to change where it goes.

Run it by hand from the Actions tab with **Run workflow** — tick `dry_run` to
build the edition and skip the send.
