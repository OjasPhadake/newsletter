# norepeat

Stop a recurring job from repeating itself — including when it rewords.

Anything that runs every day and produces content has the same failure mode:
it starts saying the same things. A newsletter re-runs a story under a
different link. A standup digest re-reports last week. An agent rediscovers
its own best idea and files it as new.

Remembering exact strings does not help, because the second telling is never
worded the same way. These are all the *same story*, and a hash or a URL
comparison catches none of them:

```
Chili's opened a fake loan office next door to a McDonald's
Chili's opened a fake payday-loan shop next door to a McDonald's

Houston fixed its baggage complaints by making passengers walk six times further
Houston's airport fixed its baggage complaints by making everyone walk further

Saturn has grown a decagon, and nobody expected to watch one form
A ten-sided storm has appeared at Saturn's south pole
```

`norepeat` catches all three.

## How

Values are remembered by *kind*, each with its own cooldown, and matched two
ways. Either most of the shorter line's content words also appear in the other
one, or the two share at least two unusual words. Both need three words in
common first, which is what stops two unrelated stories about the same
industry from colliding.

## Use

```python
from norepeat import Guard

g = Guard("state.json",
          cooldowns={"story": None, "author": 90, "source": 30},  # None = forever
          fuzzy={"story"})

collisions = g.check({"story": [headline], "source": [domain]})
for c in collisions:
    print(c.kind, c.value, c.why)

if not collisions:
    publish()
    g.record({"date": "2026-09-08", "story": [headline], "source": [domain]})
```

A weaker signal can block a stronger one. Here a brand merely mentioned in
passing yesterday blocks a headline about it today, without the mentions
themselves ever being rejected:

```python
g = Guard("state.json",
          cooldowns={"brand": 60, "mention": 60},
          not_checked={"mention"},
          also_check={"brand": ["mention"]})
```

## Command line

```bash
norepeat record --state s.json --kind story --value "Heinz put ketchup in a keg"
norepeat check  --state s.json --kind story --fuzzy --value "Heinz has put ketchup into a keg"
norepeat list   --state s.json --kind story
```

`check` exits non-zero when something repeats, so it drops into a pipeline:

```bash
norepeat check --state s.json --kind story --fuzzy --value "$HEADLINE" || exit 1
```

## Install

```bash
pip install norepeat
```

One file, standard library only — vendoring `norepeat.py` works just as well.

MIT licensed. Extracted from [The Morning](https://github.com/OjasPhadake/newsletter),
a daily newsletter written by an agent, where it is the thing that keeps the
writing fresh.
