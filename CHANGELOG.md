# Changelog

## v0.1.0 — 2026-11-04

First release.

- **One local JSON board of quotes** — client, job, amount (CAD),
  date sent, status (`open`/`won`/`lost`), last-contact date and
  follow-up count. Created by the first `add`; validated on every
  read with errors that name the offending entry. A corrupt board
  is a clean error and is **never overwritten or silently wiped**;
  saves are atomic (temp file + replace).
- **`due`** — the money view: open quotes grouped by days since
  last contact into **DUE NOW (3+)**, **STALE (7+)** and **GOING
  COLD (14+)**, oldest first, each with a ready-to-send follow-up
  line. Boundaries are exact: day 3, day 7 and day 14 land in
  their new buckets. Exits **1 when anything is due**, so a
  reminder script can act on it; 0 when every open quote is fresh.
- **Follow-up lines built only from board facts** — the client,
  the job, the amount, the sent date and the real wait, with a
  distinct repeat version that states how many follow-ups have
  already gone out. No fake urgency, no invented discounts or
  deadlines, no placeholders.
- **The clock runs from last contact, not sent date** —
  `followed <id>` records a follow-up sent today (count +1,
  last-contact = today), so a chased quote goes fresh again even
  if it was sent weeks ago. `won <id>` / `lost <id>` close a
  quote: it leaves the due view but stays in the totals.
- **Honest totals everywhere** — pipeline still open, value won,
  value lost, each with its quote count. Closed quotes can never
  be followed up or re-closed; unknown ids are clean errors.
- **`--cad-to-inr RATE`** — also prints INR equivalents next to
  every amount (the CAD + INR display pattern of payout-tracker).
- **`--json` on every command** — one JSON object with the same
  numbers and exit codes as the text view; errors are
  `{"error": ...}` objects, argparse usage errors included.
- **`--today YYYY-MM-DD`** pins the date for reproducible runs
  and reminder scripts.
- **`SKILL.md`** at the repo root for AI coding agents: commands,
  the JSON schemas, exit codes, and the honesty rules (pipeline
  is not income; a follow-up is recorded only when it was really
  sent; message lines state board facts only).
- Bundled sample board (`examples/sample-board.json`): nine
  quotes for a small website-building business at ages 1–30 days
  — including entries sitting exactly on the 3-, 7- and 14-day
  boundaries — plus one won and one lost, with $11,750 still open.
- 39 stdlib-unittest tests: hand-computed ages and bucket
  boundaries on a fixed `--today`, the follow-up clock reset,
  won/lost exclusion, corrupt-board safety (file left
  byte-identical), message-fact checks, hand-added totals, and
  JSON/text agreement.
- Pure Python standard library; local only; MIT licence.
