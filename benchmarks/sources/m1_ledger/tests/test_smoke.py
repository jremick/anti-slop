"""READ-ONLY SMOKE TEST SUITE — DO NOT MODIFY.

Covers only happy-path cases; full contract invariants are tested externally.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from m1_ledger import calculate_fee_cents, post_entries, settle_entries, summarize_currency_totals  # noqa: E402


class SmokeTests(unittest.TestCase):
    def test_happy_path_fee(self) -> None:
        self.assertEqual(calculate_fee_cents(1000, 100), 10)

    def test_happy_path_post(self) -> None:
        posted = post_entries([{"account": "acct-1", "amount_cents": 500, "currency": "USD"}])
        self.assertEqual(posted[0]["currency"], "USD")

    def test_happy_path_settle_and_report(self) -> None:
        settled = settle_entries([{"account": "acct-1", "amount_cents": 1000, "currency": "USD"}], fee_bps=100)
        self.assertEqual(settled[0]["net_cents"], 990)
        totals = summarize_currency_totals(settled)
        self.assertEqual(totals["USD"], 990)


if __name__ == "__main__":
    unittest.main()
