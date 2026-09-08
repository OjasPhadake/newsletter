# The Morning

A daily newsletter, written each morning by an agent and emailed before you
wake up. A quote, the best of Hacker News with real summaries, markets, trends
and signals, new AI research, a few wonderfully odd things companies have done,
and one thing explained in three paragraphs.

**Nothing in it ever repeats.** Not a quote, not an idea, not a story — and not
the same story reworded, or under a different outlet's link. That part is
enforced in code, not left to the agent's memory, and it is the reason this
still reads well after months rather than turning into slop.

📬 **[Read the archive](https://ojasphadake.github.io/newsletter/)** — every
issue ever sent. *(Enable Pages to publish it; see below.)*

---

## Try it in five minutes

You do not need to set up email to see what it produces.

1. **Fork this repo.**
2. Add one secret — Settings → Secrets and variables → Actions:
   `CLAUDE_CODE_OAUTH_TOKEN` (run `claude setup-token` locally to get one).
3. Actions → **The Morning** → *Run workflow* → tick **dry_run**.
4. When it finishes, download the **edition** artifact and open
   `build/edition.html`.

That builds a complete issue and skips the send. Nothing is emailed, nothing is
committed.

To render an issue with no agent and no secrets at all:

```bash
python3 scripts/build_email.py editions/2026-09-08.json > /tmp/edition.html
python3 scripts/build_archive.py && open site/index.html
```

## Make it yours

Everything personal lives in [`newsletter.toml`](newsletter.toml) — who it is
for, when it goes, which sections run, in what order. It is the only file you
have to edit.

```toml
[reader]
name  = "Ojas"
email = "you@example.com"
about = "a chemical engineering / data science student at IIT Madras"
```

`about` matters more than it looks: the editorial briefs address this person
directly, and "a mechanical engineer who reads a lot of history" produces a
different newsletter from "a founder raising a seed round".

```bash
python3 scripts/config.py          # what is actually in effect
python3 scripts/config.py --cron   # the cron line for your send time
```

A missing or malformed config falls back to built-in defaults with a warning
rather than failing a send.

## Pick a look

Five templates ship in [`templates/`](templates/) — `morning` (the default),
`broadsheet`, `digest`, `mono` and `dusk`. Set one in `newsletter.toml`:

```toml
[newsletter]
template = "digest"
```

Compare them side by side before you decide:

```bash
python3 scripts/preview_templates.py && open build/templates/index.html
```

Templates are TOML, not code: palettes, font stacks, masthead, section
headings, quote style and type scale. Copy `templates/morning.toml`, which
documents every key, to make your own. A missing or malformed template falls
back to the default look rather than failing a send.

## Sending

Pick a provider in `[sender]`, then add its secrets:

| provider | secrets | notes |
|---|---|---|
| `gmail` | `GMAIL_USER`, `GMAIL_APP_PASSWORD` | needs 2FA + an [app password](https://myaccount.google.com/apppasswords) |
| `resend` | `RESEND_API_KEY`, and `RESEND_FROM` as a *variable* | no app password; the from-domain must be verified |
| `smtp` | `SMTP_USER`, `SMTP_PASSWORD`, plus `SMTP_HOST`/`SMTP_PORT` variables | anything else |

`CLAUDE_CODE_OAUTH_TOKEN` is always required. Optionally set a `RECIPIENT`
repository variable to override `[reader].email` without editing the config.

**Cost.** Each issue is one agent run that reads 15–25 pages: roughly $1–2 of
Claude usage a day on API pricing, or included if you have a Claude subscription
the OAuth token is attached to. That is the real price of running this.

## How it works

Content and presentation are separate on purpose.

```
newsletter.toml           who it is for, when it goes, which sections run
PROMPT.md                 the editorial briefs — what makes each section good
.github/RUNBOOK_ACTIONS.md  what changes when it runs headless in CI
scripts/config.py         reads newsletter.toml, with safe fallbacks
scripts/fetch_hn.py       top-voted HN stories in a time window
scripts/fetch_papers.py   recent AI/ML/control papers, affiliation-checked
scripts/fetch_labs.py     recent posts from the labs' own research blogs
scripts/fetch_ideas.py    raw material for Ten Ideas, from Reddit and Ask HN
scripts/build_email.py    turns an edition JSON into the email HTML
scripts/build_archive.py  turns editions/ into the web archive
scripts/preview_templates.py  renders one issue in every template, to choose
templates/*.toml          the look: palettes, type, masthead, section styling
scripts/history.py        the duplicate guard, newsletter half
scripts/norepeat.py       the duplicate guard, reusable half
editions/*.json           one file per issue — the content, as data
state/history.json        what has been sent, so it never repeats itself
```

The agent's job is judgement: pick the stories, read them, write the bullets.
The renderer's job is that the result looks the same every single day.

## Adding or changing a section

Two edits, no code:

1. Add a table to `[[sections]]` in `newsletter.toml` — a `key`, a `title`, an
   `accent`, and a `render` naming a layout (`hn`, `markets`, `stories`,
   `stories_title`, `learn`, `ideas`).
2. Add a matching brief to `PROMPT.md` under the heading you named in `brief`.

The brief is the important half. `stories` will lay out anything with a
headline, a URL and bullets; what makes a section good is the paragraph telling
the agent what belongs in it and what does not.

Dropping a section is one deletion. Reordering is moving a table.

## Uniqueness

`scripts/history.py` records every quote, idea, idea prompt, HN story and link
that has been sent, and `check` hard-fails the daily run on a collision.
Quotes and ideas are barred forever; authors 90 days, idea prompts 120,
links 45.

Remembering links alone was not enough — the same story kept coming back under
a different outlet's URL, and the first week ran the Ordinary's $175 banana
twice, Chili's fake loan office twice and Houston airport's baggage walk twice.
So it also records what each item was *about*:

- **subject**, barred forever and matched *loosely*, so a reworded headline or
  another outlet's coverage of the same event still collides;
- **brand**, 60 days, for the odd-ideas section — including brands merely
  name-dropped in a bullet, which is how Burger King headlined three days after
  appearing in someone else's.

```bash
python3 scripts/history.py brief    # what today may not use — read this first
python3 scripts/history.py check editions/2026-09-08.json
python3 scripts/history.py record editions/2026-09-08.json
python3 scripts/history.py backfill # rebuild state/ from editions/
```

The daily agent commits `state/history.json` back to the repo after each send,
which is how tomorrow's run knows what yesterday used.

### Using the guard on its own

The matching half is [`norepeat`](docs/norepeat.md) — no newsletter knowledge,
one file, standard library only. Useful for anything recurring that must not
repeat itself: a standup digest, a changelog summary, a scheduled agent.

It is not on PyPI, so copy the file:

```bash
curl -O https://raw.githubusercontent.com/OjasPhadake/newsletter/main/scripts/norepeat.py
```

No dependencies, nothing to install. `pyproject.toml` will build a wheel if you
would rather package it yourself.

## Automation

The daily send runs in GitHub Actions (`.github/workflows/daily.yml`) so it
lands whether or not any machine of yours is on. The cron is set five hours
early because GitHub consistently dispatches this repo's scheduled run about
that late; `python3 scripts/config.py --cron` prints both the exact line and
the one to actually use.

`.github/workflows/pages.yml` publishes the archive. Turn it on with
Settings → Pages → Source: **GitHub Actions**, then put the resulting URL in
`[newsletter].site_url` so the RSS feed carries absolute links. It is a
separate workflow on purpose: publishing a website is not worth putting in the
path of the send.

Trigger a run by hand from the Actions tab, or by pushing a tag — `run-<n>`
sends, `run-dry-<n>` builds only.

## Design

Default look (`morning`): serif masthead, numbered section rules, warm paper
ground (`#FBF8F3`) against ink (`#23272B`). Each section owns one muted accent
— pine, indigo, moss, plum, amber, clay, iris — so the eye can find its place
without anything shouting.

Typography lives in a `<style>` block; layout stays inline, so a client that
strips `<style>` still gets a correctly structured page. Every font stack ends
in a generic family because email clients have no webfonts. Both the email and
the archive are theme-aware, and follow whichever template you picked.

## Licence

MIT — see [LICENSE](LICENSE).
