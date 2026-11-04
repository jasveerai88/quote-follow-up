#!/usr/bin/env python3
"""Tests for quote-follow-up. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

The date math is checked against hand-computed ages for a fixed
--today of 2026-11-04 — never against the tool's own output:
    last contact 2026-11-02 -> 2 days  (fresh)
    last contact 2026-11-01 -> 3 days  (DUE NOW, exact boundary)
    last contact 2026-10-29 -> 6 days  (DUE NOW)
    last contact 2026-10-28 -> 7 days  (STALE, exact boundary)
    last contact 2026-10-22 -> 13 days (STALE)
    last contact 2026-10-21 -> 14 days (GOING COLD, exact boundary)
    last contact 2026-10-05 -> 30 days (GOING COLD)
Sample-board totals by hand: open 850+1800+2400+1250+950+1600+2900
= 11,750 · won 2,200 · lost 1,100.
Both directions are covered: fresh boards exit 0, due boards exit 1,
and every broken input exits 2 with a clean message — in text AND
in --json mode — while a corrupt board file is left byte-identical.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "quote_follow_up.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import quote_follow_up as qf  # noqa: E402

TODAY = date(2026, 11, 4)
TODAY_S = "2026-11-04"


def entry(**over):
    base = {"id": 1, "client": "Test Client", "job": "Test job",
            "amount": 100.0, "sent": "2026-10-01", "status": "open",
            "last_contact": "2026-10-01", "follow_ups": 0}
    base.update(over)
    return base


def run_cli(*args):
    return subprocess.run([sys.executable, str(SRC), *args],
                          capture_output=True, text=True)


class BoardCase(unittest.TestCase):
    """Base: a temp dir + helpers to write a board and run the CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.board = Path(self.tmp.name) / "board.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_board(self, entries):
        self.board.write_text(json.dumps({"quotes": entries}),
                              encoding="utf-8")
        return str(self.board)

    def cli(self, *args):
        return run_cli(*args, "--board", str(self.board))


class TestBuckets(unittest.TestCase):
    def test_boundaries_exact(self):
        self.assertEqual(qf.bucket_of(0), "fresh")
        self.assertEqual(qf.bucket_of(2), "fresh")
        self.assertEqual(qf.bucket_of(3), "due_now")
        self.assertEqual(qf.bucket_of(6), "due_now")
        self.assertEqual(qf.bucket_of(7), "stale")
        self.assertEqual(qf.bucket_of(13), "stale")
        self.assertEqual(qf.bucket_of(14), "going_cold")
        self.assertEqual(qf.bucket_of(90), "going_cold")

    def test_ages_from_last_contact_not_sent(self):
        # sent long ago, contacted yesterday -> 1 day, fresh
        e = entry(sent="2026-09-01", last_contact="2026-11-03")
        view = qf.annotate(e, TODAY)
        self.assertEqual(view["days_since_contact"], 1)
        self.assertEqual(view["days_since_sent"], 64)
        self.assertEqual(view["bucket"], "fresh")

    def test_build_due_groups_and_orders_oldest_first(self):
        entries = [
            entry(id=1, last_contact="2026-11-03"),          # 1 fresh
            entry(id=2, last_contact="2026-11-01"),          # 3 due
            entry(id=3, last_contact="2026-10-29"),          # 6 due
            entry(id=4, last_contact="2026-10-28"),          # 7 stale
            entry(id=5, last_contact="2026-10-21"),          # 14 cold
            entry(id=6, last_contact="2026-10-05"),          # 30 cold
        ]
        buckets, fresh = qf.build_due(entries, TODAY)
        self.assertEqual([e["id"] for e in buckets["due_now"]], [3, 2])
        self.assertEqual([e["id"] for e in buckets["stale"]], [4])
        self.assertEqual([e["id"] for e in buckets["going_cold"]],
                         [6, 5])
        self.assertEqual([e["id"] for e in fresh], [1])

    def test_closed_quotes_have_no_bucket(self):
        for status in ("won", "lost"):
            view = qf.annotate(entry(status=status,
                                     last_contact="2026-09-01"), TODAY)
            self.assertIsNone(view["bucket"])
            self.assertIsNone(view["message"])


class TestMessages(unittest.TestCase):
    def test_first_follow_up_message_facts(self):
        e = entry(client="Maple Street Dental", job="Website redesign",
                  amount=1800.0, sent="2026-11-01",
                  last_contact="2026-11-01", follow_ups=0)
        msg = qf.suggested_message(e, TODAY)
        self.assertIn("Maple Street Dental", msg)
        self.assertIn("Website redesign", msg)
        self.assertIn("$1,800.00", msg)
        self.assertIn("2026-11-01", msg)
        self.assertIn("3 days ago", msg)

    def test_repeat_follow_up_message_facts(self):
        e = entry(client="Lakeside Cottages",
                  job="Seasonal booking site", amount=2900.0,
                  sent="2026-09-20", last_contact="2026-10-05",
                  follow_ups=3)
        msg = qf.suggested_message(e, TODAY)
        self.assertIn("Lakeside Cottages", msg)
        self.assertIn("$2,900.00", msg)
        self.assertIn("30 days", msg)
        self.assertIn("3 follow-ups so far", msg)

    def test_no_placeholders_no_fake_urgency(self):
        for fu in (0, 1, 5):
            msg = qf.suggested_message(entry(follow_ups=fu), TODAY)
            for bad in ("{", "}", "TODO", "XXX", "Lorem",
                        "act now", "Act now", "limited time",
                        "price goes up", "last chance", "urgent"):
                self.assertNotIn(bad, msg)

    def test_one_day_pluralization(self):
        e = entry(last_contact="2026-11-03", sent="2026-11-03")
        self.assertIn("1 day ago", qf.suggested_message(e, TODAY))
        self.assertNotIn("1 days", qf.suggested_message(e, TODAY))


class TestTotals(unittest.TestCase):
    def test_hand_computed(self):
        entries = [
            entry(id=1, amount=850.0),
            entry(id=2, amount=1800.0),
            entry(id=3, amount=2400.0, status="won"),
            entry(id=4, amount=1100.0, status="lost"),
        ]
        t = qf.compute_totals(entries)
        self.assertEqual(t["open"], {"count": 2, "amount": 2650.0})
        self.assertEqual(t["won"], {"count": 1, "amount": 2400.0})
        self.assertEqual(t["lost"], {"count": 1, "amount": 1100.0})


class TestSampleBoard(BoardCase):
    SAMPLE = EXAMPLES / "sample-board.json"

    def test_sample_due_shows_every_bucket(self):
        r = run_cli("due", "--board", str(self.SAMPLE),
                    "--today", TODAY_S)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DUE NOW — no follow-up in 3+ days (2):",
                      r.stdout)
        self.assertIn("STALE — no follow-up in 7+ days (2):",
                      r.stdout)
        self.assertIn("GOING COLD — no follow-up in 14+ days (2):",
                      r.stdout)
        # hand totals: open 11,750 · won 2,200 · lost 1,100
        self.assertIn("pipeline still open $11,750.00 (7 quote(s))",
                      r.stdout)
        self.assertIn("won $2,200.00 (1)", r.stdout)
        self.assertIn("lost $1,100.00 (1)", r.stdout)
        self.assertIn("Fresh (contacted < 3 days ago): 1", r.stdout)

    def test_sample_boundaries_land_right(self):
        r = run_cli("due", "--board", str(self.SAMPLE), "--today",
                    TODAY_S, "--json")
        data = json.loads(r.stdout)
        by_id = {}
        for name, group in data["buckets"].items():
            for e in group:
                by_id[e["id"]] = (name, e["days_since_contact"])
        self.assertEqual(by_id[2], ("due_now", 3))     # exact 3
        self.assertEqual(by_id[4], ("stale", 7))       # exact 7
        self.assertEqual(by_id[6], ("going_cold", 14))  # exact 14
        self.assertEqual([e["id"] for e in data["fresh"]], [1])
        # closed quotes are in no bucket and not in fresh
        self.assertNotIn(8, by_id)
        self.assertNotIn(9, by_id)

    def test_sample_json_totals(self):
        r = run_cli("due", "--board", str(self.SAMPLE), "--today",
                    TODAY_S, "--json")
        t = json.loads(r.stdout)["totals"]
        self.assertEqual(t["open"]["amount"], 11750.0)
        self.assertEqual(t["open"]["count"], 7)
        self.assertEqual(t["won"]["amount"], 2200.0)
        self.assertEqual(t["lost"]["amount"], 1100.0)


class TestDueCli(BoardCase):
    def test_all_fresh_exits_0(self):
        self.write_board([entry(last_contact="2026-11-03",
                                sent="2026-11-03")])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing due", r.stdout)

    def test_anything_due_exits_1(self):
        self.write_board([entry(last_contact="2026-11-01",
                                sent="2026-11-01")])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DUE NOW", r.stdout)

    def test_empty_board_exits_0(self):
        self.write_board([])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing due", r.stdout)

    def test_won_lost_excluded_from_due(self):
        self.write_board([
            entry(id=1, status="won", last_contact="2026-09-01",
                  amount=500.0),
            entry(id=2, status="lost", last_contact="2026-09-01",
                  amount=700.0),
        ])
        r = self.cli("due", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Nothing due", r.stdout)
        self.assertIn("won $500.00 (1)", r.stdout)
        self.assertIn("lost $700.00 (1)", r.stdout)

    def test_json_text_agreement(self):
        self.write_board([
            entry(id=1, amount=1800.0, last_contact="2026-11-01",
                  sent="2026-11-01"),
            entry(id=2, amount=950.0, last_contact="2026-10-22",
                  sent="2026-10-15", follow_ups=2),
            entry(id=3, amount=300.0, status="won"),
        ])
        text = self.cli("due", "--today", TODAY_S)
        js = self.cli("due", "--today", TODAY_S, "--json")
        self.assertEqual(text.returncode, js.returncode)
        data = json.loads(js.stdout)
        self.assertEqual(data["totals"]["open"]["amount"], 2750.0)
        self.assertIn("$2,750.00", text.stdout)
        self.assertEqual(len(data["buckets"]["due_now"]), 1)
        self.assertEqual(len(data["buckets"]["stale"]), 1)
        due_entry = data["buckets"]["due_now"][0]
        self.assertEqual(due_entry["message"],
                         qf.suggested_message(
                             entry(amount=1800.0,
                                   last_contact="2026-11-01",
                                   sent="2026-11-01"), TODAY))
        self.assertIn(due_entry["message"], text.stdout)

    def test_cad_to_inr(self):
        self.write_board([entry(amount=1000.0)])
        r = self.cli("list", "--today", TODAY_S, "--cad-to-inr",
                     "67.97", "--json")
        data = json.loads(r.stdout)
        # 1000 * 67.97 = 67,970
        self.assertEqual(data["totals"]["open"]["amount_inr"], 67970.0)
        self.assertEqual(data["quotes"][0]["amount_inr"], 67970.0)
        r2 = self.cli("list", "--today", TODAY_S, "--cad-to-inr",
                      "67.97")
        self.assertIn("₹67,970", r2.stdout)

    def test_bad_cad_to_inr(self):
        self.write_board([entry()])
        r = self.cli("list", "--cad-to-inr", "-5")
        self.assertEqual(r.returncode, 2)
        self.assertIn("ERROR", r.stdout)


class TestMutations(BoardCase):
    def test_add_creates_board_and_increments_ids(self):
        r = run_cli("add", "--board", str(self.board),
                    "--client", "A", "--job", "Job one",
                    "--amount", "100", "--sent", "2026-11-01")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.board.is_file())
        r = run_cli("add", "--board", str(self.board),
                    "--client", "B", "--job", "Job two",
                    "--amount", "250.50")
        self.assertEqual(r.returncode, 0)
        data = json.loads(self.board.read_text())
        self.assertEqual([q["id"] for q in data["quotes"]], [1, 2])
        self.assertEqual(data["quotes"][1]["amount"], 250.50)
        self.assertEqual(data["quotes"][0]["last_contact"],
                         "2026-11-01")
        self.assertEqual(data["quotes"][0]["status"], "open")

    def test_followed_resets_the_clock(self):
        self.write_board([entry(last_contact="2026-10-25",
                                sent="2026-10-20", follow_ups=1)])
        before = self.cli("due", "--today", TODAY_S)
        self.assertEqual(before.returncode, 1)  # 10 days -> STALE
        r = self.cli("followed", "1", "--today", TODAY_S)
        self.assertEqual(r.returncode, 0)
        saved = json.loads(self.board.read_text())["quotes"][0]
        self.assertEqual(saved["follow_ups"], 2)
        self.assertEqual(saved["last_contact"], TODAY_S)
        after = self.cli("due", "--today", TODAY_S)
        self.assertEqual(after.returncode, 0)
        self.assertIn("Nothing due", after.stdout)

    def test_won_and_lost_close_entries(self):
        self.write_board([entry(id=1, amount=400.0),
                          entry(id=2, amount=600.0)])
        self.assertEqual(self.cli("won", "1").returncode, 0)
        self.assertEqual(self.cli("lost", "2").returncode, 0)
        r = self.cli("list", "--today", TODAY_S)
        self.assertIn("won $400.00 (1)", r.stdout)
        self.assertIn("lost $600.00 (1)", r.stdout)
        self.assertIn("pipeline still open $0.00 (0 quote(s))",
                      r.stdout)

    def test_followed_on_closed_is_clean_error(self):
        self.write_board([entry(status="won")])
        r = self.cli("followed", "1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already won", r.stdout)

    def test_won_on_won_is_clean_error(self):
        self.write_board([entry(status="won")])
        r = self.cli("won", "1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("already won", r.stdout)

    def test_missing_id_is_clean_error(self):
        self.write_board([entry()])
        for cmd in ("followed", "won", "lost"):
            r = self.cli(cmd, "99")
            self.assertEqual(r.returncode, 2, cmd)
            self.assertIn("no quote with id 99", r.stdout)

    def test_missing_board_is_clean_error(self):
        r = self.cli("due")
        self.assertEqual(r.returncode, 2)
        self.assertIn("board not found", r.stdout)


class TestCorruptBoard(BoardCase):
    def test_invalid_json_errors_and_file_untouched(self):
        self.board.write_text('{"quotes": [broken', encoding="utf-8")
        before = self.board.read_bytes()
        r = self.cli("due")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid JSON", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertEqual(self.board.read_bytes(), before)

    def test_add_never_wipes_a_corrupt_board(self):
        self.board.write_text("not json at all", encoding="utf-8")
        before = self.board.read_bytes()
        r = run_cli("add", "--board", str(self.board), "--client", "A",
                    "--job", "J", "--amount", "10")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.board.read_bytes(), before)

    def test_wrong_shape_errors(self):
        self.board.write_text('{"items": []}', encoding="utf-8")
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn('"quotes" key', r.stdout)

    def test_bad_entry_names_its_position(self):
        self.write_board([entry(), entry(id=2, amount=-5.0)])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("entry 2", r.stdout)
        self.assertIn("'amount'", r.stdout)

    def test_duplicate_ids_rejected(self):
        self.write_board([entry(id=1), entry(id=1, client="Other")])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("duplicate id 1", r.stdout)

    def test_bad_status_and_bad_dates_rejected(self):
        self.write_board([entry(status="pending")])
        self.assertEqual(self.cli("list").returncode, 2)
        self.write_board([entry(sent="2026-13-40")])
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a real calendar date", r.stdout)
        self.write_board([entry(sent="Nov 1 2026")])
        self.assertEqual(self.cli("list").returncode, 2)

    def test_nan_amount_in_board_rejected(self):
        self.board.write_text(
            '{"quotes": [{"id": 1, "client": "A", "job": "J",'
            ' "amount": NaN, "sent": "2026-11-01"}]}',
            encoding="utf-8")
        r = self.cli("list")
        self.assertEqual(r.returncode, 2)


class TestCliValidation(BoardCase):
    def test_bad_today_flag(self):
        self.write_board([entry()])
        r = self.cli("due", "--today", "next friday")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--today", r.stdout)

    def test_add_rejects_nan_and_negative_amounts(self):
        for bad in ("nan", "inf", "-1"):
            r = run_cli("add", "--board", str(self.board),
                        "--client", "A", "--job", "J", "--amount", bad)
            self.assertEqual(r.returncode, 2, bad)
            self.assertFalse(self.board.exists())

    def test_add_rejects_blank_client(self):
        r = run_cli("add", "--board", str(self.board), "--client",
                    "   ", "--job", "J", "--amount", "10")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--client", r.stdout)

    def test_argparse_error_is_json_in_json_mode(self):
        r = run_cli("add", "--board", str(self.board), "--amount",
                    "10", "--json")  # missing --client and --job
        self.assertEqual(r.returncode, 2)
        self.assertIn("error", json.loads(r.stdout))

    def test_error_is_json_object_in_json_mode(self):
        r = self.cli("due", "--json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("board not found", json.loads(r.stdout)["error"])

    def test_no_command_is_clean_error(self):
        r = run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
