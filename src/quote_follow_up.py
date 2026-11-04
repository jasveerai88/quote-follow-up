#!/usr/bin/env python3
"""quote-follow-up — a local quote board that tells solo tradespeople
and contractors which quotes are going quiet, and what to send next.

Pure Python standard library. Local only: no network, no uploads, no
accounts. Your client list never leaves your machine.

Most quotes do not die because the price was wrong. They die because
nobody followed up. CRMs fix that with a monthly subscription, a
pipeline board and a hundred fields a one-person business will never
fill in. This tool is one JSON file and five commands.

The board is a single JSON file (created by your first `add`):
  {"quotes": [ {entry}, ... ]}

Entry fields:
  id           integer, assigned by `add` (never reused)
  client       who the quote went to (required, non-empty)
  job          what the quote is for (required, non-empty)
  amount       quote total in CAD (required, >= 0)
  sent         date the quote was sent, YYYY-MM-DD (required)
  status       "open" | "won" | "lost" (default "open")
  last_contact date of the last touch — a follow-up, a call, a reply
               (default: the sent date)
  follow_ups   how many follow-ups have been sent (default 0)

Commands:
  add       --client C --job J --amount A [--sent D] [--last-contact D]
            [--follow-ups N] [--status open|won|lost]
  list      every entry, plus the money totals
  due       [--today D] — open quotes grouped by how long they have
            been waiting since the last contact:
              DUE NOW    3+ days   (first follow-up is owed)
              STALE      7+ days
              GOING COLD 14+ days
            Each due entry gets a ready-to-send follow-up line that
            names the client, the job, the amount and the wait — no
            fake urgency, no invented facts.
  followed ID [--today D] — record a follow-up sent today: the count
            goes up by one and the age clock restarts from today.
  won ID / lost ID — close an entry. Closed quotes leave the due
            view but stay in the totals.

The age clock runs from `last_contact`, not `sent`: a quote you
chased yesterday is fresh even if it was sent a month ago.

Amounts are CAD. --cad-to-inr R also prints INR equivalents (rate R
per 1 CAD), following the CAD + INR display pattern of
payout-tracker.

Exit codes: 0 = ok / nothing due · 1 = `due` found at least one
quote DUE NOW or older (a finding, so a reminder script can act on
it) · 2 = ERROR — clean message, never a traceback; with --json the
error is {"error": ...}. A corrupt board is an error and is NEVER
overwritten or silently wiped.
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import date
from pathlib import Path

__version__ = "0.1.0"
TOOL = "quote-follow-up"

STATUSES = ("open", "won", "lost")
DUE_NOW_DAYS = 3
STALE_DAYS = 7
GOING_COLD_DAYS = 14
BUCKETS = ("due_now", "stale", "going_cold")
BUCKET_LABELS = {
    "due_now": "DUE NOW",
    "stale": "STALE",
    "going_cold": "GOING COLD",
}
BUCKET_BLURBS = {
    "due_now": f"no follow-up in {DUE_NOW_DAYS}+ days",
    "stale": f"no follow-up in {STALE_DAYS}+ days",
    "going_cold": f"no follow-up in {GOING_COLD_DAYS}+ days",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

def parse_date(value, label):
    """Strict YYYY-MM-DD -> date, or a clean ToolError naming `label`."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ToolError(f"{label} must be a date as YYYY-MM-DD "
                        f"(got {value!r})")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{label} is not a real calendar date: {value!r}")


def today_arg(value):
    """Resolve an optional --today flag to a date (default: today)."""
    if value is None:
        return date.today()
    return parse_date(value, "--today")


# --------------------------------------------------------------------------
# board loading + validation (a corrupt board is never wiped)
# --------------------------------------------------------------------------

def _fail_entry(no, msg):
    raise ToolError(f"entry {no}: {msg}")


def _check_amount(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise ToolError(f"{label} must be a finite number (got {value!r})")
    if value < 0:
        raise ToolError(f"{label} must be >= 0 (got {value})")
    return float(value)


def normalize_entry(raw, no):
    """Validate one raw board entry -> a clean entry dict."""
    if not isinstance(raw, dict):
        _fail_entry(no, f"expected an object of fields, got {raw!r}")
    entry_id = raw.get("id")
    if isinstance(entry_id, bool) or not isinstance(entry_id, int) \
            or entry_id < 1:
        _fail_entry(no, f"'id' must be a positive whole number "
                        f"(got {entry_id!r})")
    client = raw.get("client")
    if not isinstance(client, str) or not client.strip():
        _fail_entry(no, "'client' is required and must be a non-empty "
                        "string")
    job = raw.get("job")
    if not isinstance(job, str) or not job.strip():
        _fail_entry(no, "'job' is required and must be a non-empty "
                        "string")
    if "amount" not in raw:
        _fail_entry(no, "missing required field 'amount'")
    try:
        amount = _check_amount(raw["amount"], "'amount'")
    except ToolError as exc:
        _fail_entry(no, str(exc))
    if "sent" not in raw:
        _fail_entry(no, "missing required field 'sent'")
    try:
        sent = parse_date(raw["sent"], "'sent'")
    except ToolError as exc:
        _fail_entry(no, str(exc))
    status = raw.get("status", "open")
    if status not in STATUSES:
        _fail_entry(no, f"'status' must be one of "
                        f"{'/'.join(STATUSES)} (got {status!r})")
    last_raw = raw.get("last_contact", raw["sent"])
    try:
        last_contact = parse_date(last_raw, "'last_contact'")
    except ToolError as exc:
        _fail_entry(no, str(exc))
    follow_ups = raw.get("follow_ups", 0)
    if isinstance(follow_ups, bool) or not isinstance(follow_ups, int) \
            or follow_ups < 0:
        _fail_entry(no, f"'follow_ups' must be a whole number >= 0 "
                        f"(got {follow_ups!r})")
    return {
        "id": entry_id,
        "client": client.strip(),
        "job": job.strip(),
        "amount": amount,
        "sent": sent.isoformat(),
        "status": status,
        "last_contact": last_contact.isoformat(),
        "follow_ups": follow_ups,
    }


def _reject_json_constant(name):
    raise ValueError(f"invalid constant {name}")


def load_board(path, must_exist=True):
    """Read + validate the board file -> list of clean entry dicts.

    Raises ToolError on anything wrong. The file is only ever READ
    here; a corrupt board is reported, never repaired in place.
    """
    if not path.is_file():
        if must_exist:
            raise ToolError(f"board not found: {path} — add a quote "
                            f"first (the board is created by `add`)")
        return []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read board {path.name} "
                        f"({exc.__class__.__name__}) — the file was "
                        f"left untouched")
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ToolError(f"board {path.name} is not valid JSON: {exc} "
                        f"— the file was left untouched")
    if isinstance(data, dict):
        if "quotes" not in data:
            raise ToolError(f"board {path.name}: a JSON object must "
                            f"hold the entries under a \"quotes\" key "
                            f"— the file was left untouched")
        data = data["quotes"]
    if not isinstance(data, list):
        raise ToolError(f"board {path.name}: expected a JSON list of "
                        f"quotes (or an object with \"quotes\") — the "
                        f"file was left untouched")
    entries = [normalize_entry(raw, i + 1) for i, raw in enumerate(data)]
    seen = set()
    for e in entries:
        if e["id"] in seen:
            raise ToolError(f"board {path.name}: duplicate id "
                            f"{e['id']} — ids must be unique; the "
                            f"file was left untouched")
        seen.add(e["id"])
    return entries


def save_board(path, entries):
    """Write the board atomically (temp file in the same folder, then
    replace) so a crash mid-write can never leave a half board."""
    payload = {"quotes": entries}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise ToolError(f"could not write board {path} "
                        f"({exc.__class__.__name__}: {exc})")


# --------------------------------------------------------------------------
# the logic — ages, buckets, messages, totals
# --------------------------------------------------------------------------

def days_since(entry, field, today):
    return (today - date.fromisoformat(entry[field])).days


def bucket_of(age_days):
    """The bucket for an open quote's days since last contact.
    Boundaries are exact: 3 -> DUE NOW, 7 -> STALE, 14 -> GOING COLD."""
    if age_days >= GOING_COLD_DAYS:
        return "going_cold"
    if age_days >= STALE_DAYS:
        return "stale"
    if age_days >= DUE_NOW_DAYS:
        return "due_now"
    return "fresh"


def _days(n):
    return f"{n} day" + ("" if n == 1 else "s")


def suggested_message(entry, today):
    """A polite, specific follow-up line built ONLY from facts on the
    board: client, job, amount, the sent date and the actual wait.
    No fake urgency, no invented discounts, deadlines or demand."""
    amount = _fmt_money(entry["amount"])
    age = days_since(entry, "last_contact", today)
    if entry["follow_ups"] <= 0:
        return (f"Hi {entry['client']}, following up on the quote "
                f"for {entry['job']} ({amount}) sent on "
                f"{entry['sent']} — {_days(age)} ago now. If the "
                f"timing or the scope needs adjusting, I'm happy to "
                f"rework it; and if you've gone another way, no hard "
                f"feelings — just let me know.")
    plural = "s" if entry["follow_ups"] != 1 else ""
    return (f"Hi {entry['client']}, checking in again on the quote "
            f"for {entry['job']} ({amount}) sent on {entry['sent']}. "
            f"It's been {_days(age)} since my last note "
            f"({entry['follow_ups']} follow-up{plural} so far). Still "
            f"happy to answer questions or adjust the scope — and a "
            f"quick \"not now\" is completely fine too.")


def annotate(entry, today):
    """An entry plus its computed view fields for `today`."""
    out = dict(entry)
    out["days_since_contact"] = days_since(entry, "last_contact", today)
    out["days_since_sent"] = days_since(entry, "sent", today)
    out["bucket"] = (bucket_of(out["days_since_contact"])
                     if entry["status"] == "open" else None)
    out["message"] = (suggested_message(entry, today)
                      if out["bucket"] in BUCKETS else None)
    return out


def build_due(entries, today):
    """Group open quotes by bucket (oldest first inside each bucket)
    and collect the ones still fresh."""
    annotated = [annotate(e, today) for e in entries]
    buckets = {name: [] for name in BUCKETS}
    fresh = []
    for e in annotated:
        if e["status"] != "open":
            continue
        if e["bucket"] in buckets:
            buckets[e["bucket"]].append(e)
        else:
            fresh.append(e)
    for group in list(buckets.values()) + [fresh]:
        group.sort(key=lambda e: (-e["days_since_contact"], e["id"]))
    return buckets, fresh


def compute_totals(entries):
    totals = {s: {"count": 0, "amount": 0.0} for s in STATUSES}
    for e in entries:
        totals[e["status"]]["count"] += 1
        totals[e["status"]]["amount"] += e["amount"]
    return totals


def find_entry(entries, entry_id):
    for e in entries:
        if e["id"] == entry_id:
            return e
    raise ToolError(f"no quote with id {entry_id} on this board")


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _fmt_money(value, cad_to_inr=None):
    text = f"${value:,.2f}"
    if cad_to_inr is not None:
        text += f" (₹{value * cad_to_inr:,.0f})"
    return text


def _with_inr(obj, fields, cad_to_inr):
    if cad_to_inr is None:
        return obj
    for f in fields:
        if obj.get(f) is not None:
            obj[f + "_inr"] = round(obj[f] * cad_to_inr, 2)
    return obj


def _entry_json(e, cad_to_inr, with_view=True):
    obj = {
        "id": e["id"],
        "client": e["client"],
        "job": e["job"],
        "amount": round(e["amount"], 2),
        "sent": e["sent"],
        "status": e["status"],
        "last_contact": e["last_contact"],
        "follow_ups": e["follow_ups"],
    }
    if with_view and "days_since_contact" in e:
        obj["days_since_contact"] = e["days_since_contact"]
        obj["days_since_sent"] = e["days_since_sent"]
        obj["bucket"] = e["bucket"]
        obj["message"] = e["message"]
    return _with_inr(obj, ("amount",), cad_to_inr)


def _totals_json(totals, cad_to_inr):
    obj = {}
    for status in STATUSES:
        t = {"count": totals[status]["count"],
             "amount": round(totals[status]["amount"], 2)}
        obj[status] = _with_inr(t, ("amount",), cad_to_inr)
    return obj


def _totals_line(totals, cad_to_inr):
    o, w, l = totals["open"], totals["won"], totals["lost"]
    return (f"TOTALS: pipeline still open "
            f"{_fmt_money(o['amount'], cad_to_inr)} "
            f"({o['count']} quote(s)) · won "
            f"{_fmt_money(w['amount'], cad_to_inr)} ({w['count']}) · "
            f"lost {_fmt_money(l['amount'], cad_to_inr)} "
            f"({l['count']})")


def _header(command, board_name, today, cad_to_inr):
    lines = [
        f"quote-follow-up v{__version__} — {command} · board "
        f"{board_name} · today {today.isoformat()}",
        "Amounts in CAD."
        + (f" INR equivalents at {cad_to_inr:g} per CAD dollar."
           if cad_to_inr is not None else ""),
    ]
    return lines


def _entry_line(e, cad_to_inr):
    return (f"#{e['id']} · {e['client']} — {e['job']} — "
            f"{_fmt_money(e['amount'], cad_to_inr)} — sent "
            f"{e['sent']}, last contact {e['last_contact']} "
            f"({_days(e['days_since_contact'])} ago), "
            f"{e['follow_ups']} follow-up(s)"
            + ("" if e["status"] == "open" else f" [{e['status']}]"))


def render_due_text(buckets, fresh, totals, board_name, today,
                    cad_to_inr):
    lines = _header("due", board_name, today, cad_to_inr)
    lines.append("")
    due_count = sum(len(buckets[b]) for b in BUCKETS)
    if due_count == 0:
        lines.append("Nothing due — every open quote was contacted "
                     f"within the last {DUE_NOW_DAYS} days.")
    for name in BUCKETS:
        group = buckets[name]
        if not group:
            continue
        lines.append(f"{BUCKET_LABELS[name]} — {BUCKET_BLURBS[name]} "
                     f"({len(group)}):")
        for e in group:
            lines.append(_entry_line(e, cad_to_inr))
            lines.append(f"   → {e['message']}")
        lines.append("")
    lines.append(_totals_line(totals, cad_to_inr))
    lines.append(f"Fresh (contacted < {DUE_NOW_DAYS} days ago): "
                 f"{len(fresh)} · Due now or older: {due_count}")
    return "\n".join(lines)


def due_as_json(buckets, fresh, totals, board_name, today, cad_to_inr):
    return {
        "tool": TOOL, "version": __version__, "command": "due",
        "board": board_name, "today": today.isoformat(),
        "cad_to_inr": cad_to_inr,
        "buckets": {name: [_entry_json(e, cad_to_inr)
                           for e in buckets[name]] for name in BUCKETS},
        "fresh": [_entry_json(e, cad_to_inr) for e in fresh],
        "totals": _totals_json(totals, cad_to_inr),
    }


def render_list_text(annotated, totals, board_name, today, cad_to_inr):
    lines = _header("list", board_name, today, cad_to_inr)
    lines.append("")
    if not annotated:
        lines.append("No quotes on this board yet — add one with "
                     "`add`.")
    for e in sorted(annotated, key=lambda x: x["id"]):
        lines.append(_entry_line(e, cad_to_inr))
    lines.append("")
    lines.append(_totals_line(totals, cad_to_inr))
    return "\n".join(lines)


def list_as_json(annotated, totals, board_name, today, cad_to_inr):
    return {
        "tool": TOOL, "version": __version__, "command": "list",
        "board": board_name, "today": today.isoformat(),
        "cad_to_inr": cad_to_inr,
        "quotes": [_entry_json(e, cad_to_inr)
                   for e in sorted(annotated, key=lambda x: x["id"])],
        "totals": _totals_json(totals, cad_to_inr),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in --json mode
    ({"error": ...} on stdout, same exit code 2) — an agent driving
    this tool with --json never gets plain text or a traceback. The
    flag lives on the class so subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _cad_to_inr(a):
    rate = getattr(a, "cad_to_inr", None)
    if rate is None:
        return None
    if not math.isfinite(rate) or rate <= 0:
        raise ToolError(f"--cad-to-inr must be a positive finite "
                        f"number (got {rate!r})")
    return rate


def _board_arg(p):
    p.add_argument("--board", default="quotes.json",
                   help="board file (default: quotes.json in the "
                        "current folder)")


def _json_arg(p):
    p.add_argument("--json", action="store_true",
                   help="print one JSON object instead of text")


def _inr_arg(p):
    p.add_argument("--cad-to-inr", type=float, default=None,
                   help="also print INR equivalents at this rate per "
                        "1 CAD dollar")


def _today_arg(p):
    p.add_argument("--today", default=None,
                   help="pretend today is this date (YYYY-MM-DD) — "
                        "for reminder scripts and tests")


def cmd_add(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path, must_exist=False)
    today = date.today()
    sent = (parse_date(a.sent, "--sent") if a.sent else today)
    last_contact = (parse_date(a.last_contact, "--last-contact")
                    if a.last_contact else sent)
    amount = _check_amount(a.amount, "--amount")
    if a.follow_ups < 0:
        raise ToolError(f"--follow-ups must be >= 0 (got {a.follow_ups})")
    entry = {
        "id": max((e["id"] for e in entries), default=0) + 1,
        "client": a.client.strip(),
        "job": a.job.strip(),
        "amount": amount,
        "sent": sent.isoformat(),
        "status": a.status,
        "last_contact": last_contact.isoformat(),
        "follow_ups": a.follow_ups,
    }
    if not entry["client"]:
        raise ToolError("--client must be a non-empty string")
    if not entry["job"]:
        raise ToolError("--job must be a non-empty string")
    entries.append(entry)
    save_board(path, entries)
    view = annotate(entry, today_arg(a.today))
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__, "command": "add",
            "board": path.name, "cad_to_inr": cad_to_inr,
            "quote": _entry_json(view, cad_to_inr),
        }, indent=2))
    else:
        print(f"Added quote #{entry['id']}: {entry['client']} — "
              f"{entry['job']} — {_fmt_money(amount, cad_to_inr)} "
              f"(sent {entry['sent']}, status {entry['status']})")
        print(f"Board: {path.name} ({len(entries)} quote(s))")
    return 0


def cmd_list(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    annotated = [annotate(e, today) for e in entries]
    totals = compute_totals(entries)
    if a.json:
        print(json.dumps(list_as_json(annotated, totals, path.name,
                                      today, cad_to_inr), indent=2))
    else:
        print(render_list_text(annotated, totals, path.name, today,
                               cad_to_inr))
    return 0


def cmd_due(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    buckets, fresh = build_due(entries, today)
    totals = compute_totals(entries)
    if a.json:
        print(json.dumps(due_as_json(buckets, fresh, totals, path.name,
                                     today, cad_to_inr), indent=2))
    else:
        print(render_due_text(buckets, fresh, totals, path.name,
                              today, cad_to_inr))
    return 1 if any(buckets[b] for b in BUCKETS) else 0


def cmd_followed(a):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    entry = find_entry(entries, a.id)
    if entry["status"] != "open":
        raise ToolError(f"quote #{a.id} is already {entry['status']} "
                        f"— closed quotes cannot be followed up")
    entry["follow_ups"] += 1
    entry["last_contact"] = today.isoformat()
    save_board(path, entries)
    view = annotate(entry, today)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "followed", "board": path.name,
            "today": today.isoformat(), "cad_to_inr": cad_to_inr,
            "quote": _entry_json(view, cad_to_inr),
        }, indent=2))
    else:
        print(f"Follow-up #{entry['follow_ups']} recorded for quote "
              f"#{entry['id']}: {entry['client']} — {entry['job']} — "
              f"{_fmt_money(entry['amount'], cad_to_inr)}")
        print(f"Last contact is now {entry['last_contact']} — the "
              f"age clock restarts from today.")
    return 0


def _cmd_close(a, new_status):
    cad_to_inr = _cad_to_inr(a)
    path = Path(a.board)
    entries = load_board(path)
    today = today_arg(a.today)
    entry = find_entry(entries, a.id)
    if entry["status"] != "open":
        raise ToolError(f"quote #{a.id} is already {entry['status']} "
                        f"— it cannot be marked {new_status}")
    entry["status"] = new_status
    save_board(path, entries)
    totals = compute_totals(entries)
    view = annotate(entry, today)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": new_status, "board": path.name,
            "today": today.isoformat(), "cad_to_inr": cad_to_inr,
            "quote": _entry_json(view, cad_to_inr),
            "totals": _totals_json(totals, cad_to_inr),
        }, indent=2))
    else:
        print(f"Quote #{entry['id']} marked {new_status.upper()}: "
              f"{entry['client']} — {entry['job']} — "
              f"{_fmt_money(entry['amount'], cad_to_inr)}")
        print(_totals_line(totals, cad_to_inr))
    return 0


def cmd_won(a):
    return _cmd_close(a, "won")


def cmd_lost(a):
    return _cmd_close(a, "lost")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="A local quote board for solo tradespeople and "
                    "contractors: which quotes are going quiet, and "
                    "the follow-up line to send next (stdlib only, "
                    "local only).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_add = sub.add_parser(
        "add", help="add a quote to the board (creates the board "
                    "file on first add)")
    p_add.add_argument("--client", required=True,
                       help="who the quote went to")
    p_add.add_argument("--job", required=True,
                       help="what the quote is for")
    p_add.add_argument("--amount", type=float, required=True,
                       help="quote total in CAD (>= 0)")
    p_add.add_argument("--sent", default=None,
                       help="date sent, YYYY-MM-DD (default: today)")
    p_add.add_argument("--last-contact", default=None,
                       help="date of last touch, YYYY-MM-DD "
                            "(default: the sent date)")
    p_add.add_argument("--follow-ups", type=int, default=0,
                       help="follow-ups already sent (default 0)")
    p_add.add_argument("--status", choices=STATUSES, default="open",
                       help="open, won or lost (default open)")
    _today_arg(p_add)
    _board_arg(p_add)
    _json_arg(p_add)
    _inr_arg(p_add)
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser(
        "list", help="every quote on the board, plus the money "
                     "totals")
    _today_arg(p_list)
    _board_arg(p_list)
    _json_arg(p_list)
    _inr_arg(p_list)
    p_list.set_defaults(func=cmd_list)

    p_due = sub.add_parser(
        "due", help="open quotes grouped by age since last contact, "
                    "each with a follow-up line to send; exit 1 when "
                    "anything is due")
    _today_arg(p_due)
    _board_arg(p_due)
    _json_arg(p_due)
    _inr_arg(p_due)
    p_due.set_defaults(func=cmd_due)

    p_fol = sub.add_parser(
        "followed", help="record a follow-up sent today for a quote "
                         "(count +1, age clock restarts)")
    p_fol.add_argument("id", type=int, help="quote id (see `list`)")
    _today_arg(p_fol)
    _board_arg(p_fol)
    _json_arg(p_fol)
    _inr_arg(p_fol)
    p_fol.set_defaults(func=cmd_followed)

    p_won = sub.add_parser("won", help="mark a quote won (closed)")
    p_won.add_argument("id", type=int, help="quote id (see `list`)")
    _today_arg(p_won)
    _board_arg(p_won)
    _json_arg(p_won)
    _inr_arg(p_won)
    p_won.set_defaults(func=cmd_won)

    p_lost = sub.add_parser("lost", help="mark a quote lost (closed)")
    p_lost.add_argument("id", type=int, help="quote id (see `list`)")
    _today_arg(p_lost)
    _board_arg(p_lost)
    _json_arg(p_lost)
    _inr_arg(p_lost)
    p_lost.set_defaults(func=cmd_lost)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
