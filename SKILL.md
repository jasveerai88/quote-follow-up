---
name: quote-follow-up
description: Track sent quotes on one local JSON board and surface which open quotes are going quiet — grouped DUE NOW (3+ days since last contact), STALE (7+), GOING COLD (14+) — each with a polite, fact-only follow-up line to send, plus honest totals (pipeline still open, won, lost) in CAD with optional INR equivalents. Use when a solo tradesperson, contractor or freelancer sends quotes and loses jobs to silence, and a CRM is overkill. Exit 1 from `due` means something is due — it is a finding, not a failure.
---

# quote-follow-up — agent skill

## Purpose

Quotes usually die from silence, not price: the client meant to
reply, got busy, and booked whoever followed up first. This tool
keeps one local JSON board of quotes and answers, on demand:
which open quotes have gone too long without a touch, how long
exactly, and what to send next. The age clock runs from
**last contact**, not from the sent date — recording a follow-up
restarts the clock. Pure Python standard library; local only;
the board file is the only thing it reads or writes.

**The honesty core of this tool:** the "pipeline still open"
total is money that has been *asked for*, not money earned. Only
the `won` total is booked work, and the `lost` total is gone.
Never present an open pipeline as income, and never let a
going-cold quote sit in a summary as if it were as good as a
fresh one.

## When to use / not use

Use when:
- A solo tradesperson / contractor / freelancer sends quotes and
  needs to know who to chase today.
- An agent maintains the board: add quotes when they are sent,
  record follow-ups, close quotes won or lost.
- A reminder script or cron needs a yes/no "is anything due?"
  signal (`due` exit code 1 = yes).

Do NOT use when:
- The business needs pipeline stages, shared/multi-user access,
  or automatic sending — that is a CRM's job; this tool reminds
  and drafts, it never sends.
- Quotes are in multiple currencies — the board is CAD (INR
  figures are display equivalents only, via `--cad-to-inr`).

## Commands

Every command takes `--board FILE` (default `quotes.json`) and
`--json`. `list`, `due`, `add`, `followed`, `won`, `lost` also
take `--cad-to-inr RATE`; view/mutation commands take
`--today YYYY-MM-DD` to pin the date.

```bash
# Add a quote (creates the board on first add)
python3 src/quote_follow_up.py add --client "Maple Street Dental" \
    --job "Website redesign" --amount 1800 [--sent 2026-11-01] \
    [--last-contact 2026-11-01] [--follow-ups 0] \
    [--status open|won|lost]

# The money view: buckets + follow-up lines (exit 1 if any due)
python3 src/quote_follow_up.py due [--today 2026-11-04]

# Everything on the board, with totals
python3 src/quote_follow_up.py list

# Record a follow-up sent today (count +1, clock restarts)
python3 src/quote_follow_up.py followed 4

# Close a quote
python3 src/quote_follow_up.py won 8
python3 src/quote_follow_up.py lost 9
```

Board entries: `id` (assigned by `add`), `client` (required),
`job` (required), `amount` (CAD, ≥ 0, required), `sent`
(YYYY-MM-DD, required), `status` (`open`|`won`|`lost`),
`last_contact` (YYYY-MM-DD, defaults to `sent`), `follow_ups`
(int ≥ 0, default 0). The board is validated on every read; a
corrupt board is a clean error and is never overwritten.

## Buckets (boundaries are exact)

Age = today − `last_contact`, in whole days, open quotes only.

| Bucket | Age | JSON key |
|---|---|---|
| fresh | 0–2 days | (listed under `fresh`) |
| DUE NOW | 3–6 days | `due_now` |
| STALE | 7–13 days | `stale` |
| GOING COLD | 14+ days | `going_cold` |

Inside a bucket, entries are ordered oldest first.

## Output JSON schema (`--json`)

Common fields: `tool` (`"quote-follow-up"`), `version`,
`command`, `board` (file name), `cad_to_inr` (rate or null);
`due`/`list`/`followed`/`won`/`lost` add `today`.

Entry objects: `id`, `client`, `job`, `amount`, `sent`, `status`,
`last_contact`, `follow_ups`, plus the computed view fields
`days_since_contact`, `days_since_sent`, `bucket` (`"due_now"` |
`"stale"` | `"going_cold"` | `"fresh"` | null for closed quotes)
and `message` (the suggested follow-up line, or null when not
due). With `--cad-to-inr`, money fields gain `*_inr` siblings.

`due`: `buckets` (`due_now`, `stale`, `going_cold` — arrays of
entry objects), `fresh` (array), `totals`.
`list`: `quotes` (all entries by id), `totals`.
`add`: `quote` (the new entry). `followed`: `quote` (updated).
`won` / `lost`: `quote` (updated) + `totals`.
`totals`: `open` / `won` / `lost`, each `{count, amount}`.

On error, stdout is a single object: `{"error": "<message>"}`
(board validation errors name the entry: `"entry 2: ..."`) with
exit code 2 — including argparse usage errors in `--json` mode.
Never plain text, never a traceback.

## Exit codes

- `0` — command succeeded; for `due`, nothing is due (every open
  quote was contacted within the last 3 days, or the board has no
  open quotes).
- `1` — `due` only: at least one open quote is DUE NOW or older.
  This is the tool working — surface who is due, oldest first.
- `2` — ERROR: board missing (for read/close commands), board
  corrupt (file left untouched), unknown id, closing or following
  up an already-closed quote, invalid date/amount/flag. No board
  change was made; do not quote numbers from a failed run.

## Limits & honesty rules the agent must respect

- **Pipeline is not income.** Report `totals.open` as quotes
  still awaiting an answer, `totals.won` as booked, `totals.lost`
  as gone. If you quote the open total, name its age mix too —
  going-cold money is a countdown, not an asset.
- **Message lines contain only board facts.** The suggested
  `message` names the client, job, amount, sent date and the real
  wait — nothing else. Never edit in a discount, a deadline, an
  "offer expires" or any urgency the user did not actually set.
  If you draft your own follow-up instead, hold it to the same
  rule.
- **A follow-up is recorded only when it was really sent.** Run
  `followed` after the user (or you, on instruction) actually
  sent the message — never to make the board look tidy. The
  follow-up count and last-contact date are the record; falsifying
  them falsifies every later bucket.
- **Closed is closed.** Won/lost quotes never re-enter the due
  view. If a lost client comes back, that is a new quote — `add`
  it; do not resurrect the old entry.
- **Exit 1 is a finding.** When `due` exits 1, report the due
  quotes by client and days waiting; do not describe the board as
  "all clear".
- Local only: the tool reads/writes only the board file named
  with `--board` and sends nothing anywhere.
