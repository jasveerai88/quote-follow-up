# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** quote-follow-up's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only.** No network calls, no telemetry, no uploads of
  user files. The tool reminds and drafts — it never sends
  messages for the user.
- **The board is the user's livelihood data.** A change that can
  lose, corrupt or silently rewrite board entries will not be
  merged. Loading must keep validating every entry; saving must
  stay atomic; a corrupt board must stay an error, never a wipe.
- **The clock stays honest.** Age is days since `last_contact`,
  and the bucket boundaries (3 / 7 / 14) are a stated product
  choice. Changing them is a behaviour change: it needs the
  README table, the changelog, the SKILL.md schema and the
  boundary tests updated together.
- **Message lines state board facts only.** No urgency, discount
  or deadline wording may enter the suggested follow-ups unless
  it comes from a field on the board. Tests assert the absence of
  fake-urgency phrasing — keep them passing.
- **Both directions tested.** A behaviour change needs a test
  where good input succeeds and bad input fails cleanly — not
  just one side. Date math needs hand-computed ages against a
  fixed `--today`, not ages copied from the tool's own output.

## Getting started

```bash
git clone https://github.com/jasveerai88/quote-follow-up
cd quote-follow-up
python3 -m unittest discover -s tests -v
python3 src/quote_follow_up.py due --board examples/sample-board.json \
    --today 2026-11-04
```

## Pull requests

1. Fork, branch, and keep the change to one topic.
2. Add or update tests under `tests/`; the full suite must pass.
3. Note the change in `CHANGELOG.md` under an "Unreleased" heading.
4. Describe the behaviour change with a real before/after run if
   the CLI output changes.
