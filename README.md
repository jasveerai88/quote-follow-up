# quote-follow-up

**Most quotes die from silence, not price.**

You sent the quote on Tuesday. The client meant to reply — then
their week happened. By the time you remember to chase it, three
weeks have passed, the job has gone to whoever followed up first,
and the quote becomes one more "they never got back to me." The
fix is not a CRM: it is a monthly subscription, a pipeline board
and a hundred fields a one-person business will never fill in.
The fix is knowing, today, exactly which quotes are going quiet —
and having the next message already written.

`quote-follow-up` is one JSON board file and five commands. It
groups your open quotes by how long they have been waiting since
your last contact — **DUE NOW** (3+ days), **STALE** (7+ days),
**GOING COLD** (14+ days) — writes a polite, specific follow-up
line for each one that you can copy and send, and keeps the money
totals honest: pipeline still open, value won, value lost.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your client list never leaves your machine
- Script-friendly exit codes: `0` = nothing due, `1` = something
  is due (so a reminder script can act on it), `2` = error

## The one idea: the clock runs from last contact

A quote's age is counted from the **last time you touched it** —
a follow-up, a call, a reply — not from the day it was sent. A
quote sent a month ago that you chased yesterday is fresh. A quote
sent four days ago that nobody has touched since is already due.
Recording a follow-up (`followed`) restarts that quote's clock,
so the board always shows who is *actually* waiting on you now.

| Bucket | Days since last contact | Meaning |
|---|---|---|
| fresh | 0–2 | Leave it alone |
| DUE NOW | 3–6 | The first follow-up is owed |
| STALE | 7–13 | It is slipping — chase it today |
| GOING COLD | 14+ | Last realistic chance before it dies quietly |

Boundaries are exact: day 3 is DUE NOW, day 7 is STALE, day 14 is
GOING COLD.

## The board file

One JSON file (default `quotes.json`, created by your first
`add`; every command takes `--board FILE`):

```json
{"quotes": [
  {"id": 1, "client": "Maple Street Dental", "job": "Website redesign",
   "amount": 1800.0, "sent": "2026-11-01", "status": "open",
   "last_contact": "2026-11-01", "follow_ups": 0}
]}
```

| Field | Meaning |
|---|---|
| `id` | assigned by `add`, never reused |
| `client` | who the quote went to (required) |
| `job` | what the quote is for (required) |
| `amount` | quote total in CAD (required, ≥ 0) |
| `sent` | date sent, `YYYY-MM-DD` (required) |
| `status` | `open` · `won` · `lost` |
| `last_contact` | date of the last touch (defaults to `sent`) |
| `follow_ups` | follow-ups sent so far (default 0) |

You can edit the file by hand — it is validated on every read.
A corrupt board is a clean error that names the problem entry,
and the file is **never** overwritten or silently wiped; writes
are atomic (temp file + replace), so a crash mid-save cannot
leave you half a board.

## The follow-up lines

Every due quote gets a ready-to-send message built **only** from
facts on the board — the client, the job, the amount, the sent
date and the real wait. No fake urgency, no invented discounts or
deadlines, no "just bumping this to the top of your inbox":

> Hi Maple Street Dental, following up on the quote for Website
> redesign ($1,800.00) sent on 2026-11-01 — 3 days ago now. If the
> timing or the scope needs adjusting, I'm happy to rework it; and
> if you've gone another way, no hard feelings — just let me know.

Quotes that have already been chased get the repeat version, which
says plainly how many follow-ups have gone out — and gives the
client an easy, no-hard-feelings way to say no. A graceful "not
now" is worth more than another month of silence: it closes the
quote honestly instead of letting it rot in the pipeline total.

## Usage

```bash
# 1. Add a quote (creates the board on first add)
python3 src/quote_follow_up.py add --client "Maple Street Dental" \
    --job "Website redesign" --amount 1800 --sent 2026-11-01

# 2. The money view: what is due, grouped by age, with the lines
python3 src/quote_follow_up.py due --board examples/sample-board.json \
    --today 2026-11-04

# 3. See everything, with the totals
python3 src/quote_follow_up.py list --board examples/sample-board.json \
    --today 2026-11-04

# 4. You sent the follow-up — record it (count +1, clock restarts)
python3 src/quote_follow_up.py followed 4 \
    --board examples/sample-board.json

# 5. Close quotes when they land or die
python3 src/quote_follow_up.py won 8 --board examples/sample-board.json
python3 src/quote_follow_up.py lost 9 --board examples/sample-board.json

# 6. Also print INR equivalents (rate per 1 CAD dollar)
python3 src/quote_follow_up.py due --board examples/sample-board.json \
    --today 2026-11-04 --cad-to-inr 67.97

# 7. Drive a reminder: exit 1 means something is due
python3 src/quote_follow_up.py due || echo "time to follow up"
```

`--today YYYY-MM-DD` pretends today is that date — the bundled
sample uses fixed dates, so its demos pass `--today 2026-11-04`
to stay reproducible. Day to day you omit it and the real date is
used.

## Use with AI agents

Every command takes `--json`: one JSON object with the same
numbers and exit codes as the text view (errors come back as
`{"error": ...}`):

```bash
python3 src/quote_follow_up.py due --board examples/sample-board.json \
    --today 2026-11-04 --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the full JSON
schemas, exit codes, and the honesty rules (the pipeline total is
not income; a message line may only state facts from the board).

## Real run (verbatim)

The bundled sample board holds nine quotes for a small
website-building business, at ages from 1 to 30 days, plus one won
and one lost. Against `--today 2026-11-04`:

```text
$ python3 src/quote_follow_up.py due --board examples/sample-board.json --today 2026-11-04
quote-follow-up v0.1.0 — due · board sample-board.json · today 2026-11-04
Amounts in CAD.

DUE NOW — no follow-up in 3+ days (2):
#3 · Okanagan Realty Group — Property listing site — $2,400.00 — sent 2026-10-28, last contact 2026-10-30 (5 days ago), 1 follow-up(s)
   → Hi Okanagan Realty Group, checking in again on the quote for Property listing site ($2,400.00) sent on 2026-10-28. It's been 5 days since my last note (1 follow-up so far). Still happy to answer questions or adjust the scope — and a quick "not now" is completely fine too.
#2 · Maple Street Dental — Website redesign — $1,800.00 — sent 2026-11-01, last contact 2026-11-01 (3 days ago), 0 follow-up(s)
   → Hi Maple Street Dental, following up on the quote for Website redesign ($1,800.00) sent on 2026-11-01 — 3 days ago now. If the timing or the scope needs adjusting, I'm happy to rework it; and if you've gone another way, no hard feelings — just let me know.

STALE — no follow-up in 7+ days (2):
#5 · Kelowna Auto Detail — Booking page — $950.00 — sent 2026-10-15, last contact 2026-10-22 (13 days ago), 2 follow-up(s)
   → Hi Kelowna Auto Detail, checking in again on the quote for Booking page ($950.00) sent on 2026-10-15. It's been 13 days since my last note (2 follow-ups so far). Still happy to answer questions or adjust the scope — and a quick "not now" is completely fine too.
#4 · Sunrise Bakery — Online ordering page — $1,250.00 — sent 2026-10-25, last contact 2026-10-28 (7 days ago), 1 follow-up(s)
   → Hi Sunrise Bakery, checking in again on the quote for Online ordering page ($1,250.00) sent on 2026-10-25. It's been 7 days since my last note (1 follow-up so far). Still happy to answer questions or adjust the scope — and a quick "not now" is completely fine too.

GOING COLD — no follow-up in 14+ days (2):
#7 · Lakeside Cottages — Seasonal booking site — $2,900.00 — sent 2026-09-20, last contact 2026-10-05 (30 days ago), 3 follow-up(s)
   → Hi Lakeside Cottages, checking in again on the quote for Seasonal booking site ($2,900.00) sent on 2026-09-20. It's been 30 days since my last note (3 follow-ups so far). Still happy to answer questions or adjust the scope — and a quick "not now" is completely fine too.
#6 · NorthPeak Fitness — Class schedule site — $1,600.00 — sent 2026-10-18, last contact 2026-10-21 (14 days ago), 1 follow-up(s)
   → Hi NorthPeak Fitness, checking in again on the quote for Class schedule site ($1,600.00) sent on 2026-10-18. It's been 14 days since my last note (1 follow-up so far). Still happy to answer questions or adjust the scope — and a quick "not now" is completely fine too.

TOTALS: pipeline still open $11,750.00 (7 quote(s)) · won $2,200.00 (1) · lost $1,100.00 (1)
Fresh (contacted < 3 days ago): 1 · Due now or older: 6
(exit code: 1 — six quotes are due)
```

Read what the board is really saying: $11,750 is still "open",
but $4,500 of it (the two GOING COLD quotes) has been waiting 14+
days — that money is not a pipeline, it is a countdown. The won
and lost quotes stay in the totals but never appear in the due
view: closed is closed.

The full loop on a scratch board, verbatim:

```text
$ python3 src/quote_follow_up.py add --board /tmp/demo-board.json --client "Maple Street Dental" --job "Website redesign" --amount 1800 --sent 2026-11-01
Added quote #1: Maple Street Dental — Website redesign — $1,800.00 (sent 2026-11-01, status open)
Board: demo-board.json (1 quote(s))

$ python3 src/quote_follow_up.py followed 1 --board /tmp/demo-board.json --today 2026-11-04
Follow-up #1 recorded for quote #1: Maple Street Dental — Website redesign — $1,800.00
Last contact is now 2026-11-04 — the age clock restarts from today.

$ python3 src/quote_follow_up.py won 1 --board /tmp/demo-board.json --today 2026-11-04
Quote #1 marked WON: Maple Street Dental — Website redesign — $1,800.00
TOTALS: pipeline still open $0.00 (0 quote(s)) · won $1,800.00 (1) · lost $0.00 (0)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 39 tests — OK
```

The suite covers both directions: the bucket boundaries are
checked at the exact days (2 fresh, 3 DUE NOW, 7 STALE, 14 GOING
COLD) against a fixed `--today`, with ages worked out by hand;
a follow-up is proven to reset the clock (STALE → fresh, exit 1 →
0); won/lost quotes are excluded from the due view but stay in
the totals; the sample board's totals match hand-added numbers
(open 11,750 · won 2,200 · lost 1,100); message lines are checked
to contain the real client, job and amount with no placeholders
and no fake-urgency wording; a corrupt board errors cleanly and
is left byte-identical (and `add` refuses to wipe it); and the
JSON and text views are asserted to agree on totals, buckets and
exit codes.

## Internal use

This tool does a real job for its author: it is the quote board
for **Focus Brilliant**, the author's own website-building service
for local businesses. Every website quote that goes out is added
to the board the day it is sent, and `due` is the checklist that
decides who gets chased before the quote goes cold.

## Known limits

- One board, one business: there are no per-user views, tags or
  pipelines — deliberately. If you need stages and automations,
  you have outgrown this tool and a CRM is honestly the answer.
- It reminds; it does not send. The follow-up lines are for you to
  copy into your own email or messages — the tool has no accounts
  and sends nothing.
- Amounts are CAD only (with optional INR display equivalents via
  `--cad-to-inr`); the board does not do multi-currency books.
- `followed` records a follow-up *you* sent; the tool cannot know
  about replies unless you update `last_contact` by hand-editing
  the board or re-adding the touch with `followed`.

## Privacy

What it touches: only the board file you point it at. What it
sends: nothing — there is no network code in this tool.

## Support

If this rescues one quote that was about to die of silence,
consider sponsoring: **https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
