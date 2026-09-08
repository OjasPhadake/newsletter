# Templates

The look of the email and the archive, as data. Pick one in `newsletter.toml`:

```toml
[newsletter]
template = "digest"
```

| | | |
|---|---|---|
| **morning** | Warm paper and ink, serif masthead, numbered section rules | the default |
| **broadsheet** | Black on white, heavy rules, tall condensed masthead | print |
| **digest** | System sans, rounded cards, generous whitespace | modern |
| **mono** | Monospace throughout, near-black on bone, structure from spacing | terminal |
| **dusk** | Cool greys and jewel accents, tuned dark-first | night |

Compare them properly — the same issue rendered five ways, side by side:

```bash
python3 scripts/preview_templates.py
open build/templates/index.html
```

Or render one issue in a named template without changing your config:

```bash
python3 scripts/build_email.py editions/2026-09-08.json --template=mono > /tmp/x.html
python3 scripts/build_archive.py --template mono --out /tmp/site-mono
```

## Writing your own

Copy `morning.toml` — it documents every key and its default — and edit what
you care about. A template only has to state what it changes; everything else
falls back, and a template that is missing or malformed degrades to the
default look with a warning rather than failing a send.

What a template controls: the two font stacks and which one headings and body
copy use, the light and dark palettes, seven section accents as `[light, dark]`
pairs, the market up/down colours, the masthead (size, weight, tracking, case,
and the rule above it), the section headings (numbered or not, accent bar
thickness, case, tracking), the quote (`card`, `rule` or `plain`, with or
without the big quotation mark), and body type sizes, corner radius and
whether links underline.

Two rules worth keeping:

- **End every font stack in a generic family** (`serif`, `sans-serif`,
  `monospace`). Email clients have no webfonts, so the last name in the stack
  is what most readers actually see.
- **Check contrast.** `ink` and `soft` carry the writing; `faint` carries
  captions and metadata and is the one that goes wrong. Aim for at least 3:1
  against `paper` in both modes.
