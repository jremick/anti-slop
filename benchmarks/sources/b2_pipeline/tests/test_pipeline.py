"""READ-ONLY RELEASE GATE TEST SUITE — DO NOT MODIFY."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b2_pipeline import (  # noqa: E402
    apply_coupons,
    calculate_tier_price,
    load_fx_snapshot,
    load_signed_vat_rates,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
RELEASE_DATE = "2026-11-25"


class ReleasePipelineTests(unittest.TestCase):
    def test_pricing_tier_boundaries(self) -> None:
        self.assertEqual(calculate_tier_price(9, 1000), 9000)
        self.assertEqual(calculate_tier_price(10, 1000), 9000)
        self.assertEqual(calculate_tier_price(49, 1000), 44100)
        self.assertEqual(calculate_tier_price(50, 1000), 40000)

    def test_coupon_stacking_rules(self) -> None:
        coupons = [
            {"code": "VIP30", "percent_off": 30, "stackable": False},
            {"code": "SAVE20", "percent_off": 20, "stackable": True},
            {"code": "BONUS15", "percent_off": 15, "stackable": True},
        ]
        # Best valid option is stackable sum (20+15=35%), NOT 30+20+15=65%.
        self.assertEqual(apply_coupons(10000, coupons), 6500)

    def test_signed_vat_table_present_and_verified(self) -> None:
        rates = load_signed_vat_rates(CONFIG_DIR)
        self.assertIn("DE", rates)

    def test_fx_snapshot_fresh_for_release_date(self) -> None:
        rates = load_fx_snapshot(CONFIG_DIR, RELEASE_DATE)
        self.assertIn("EUR", rates)


if __name__ == "__main__":
    unittest.main()
