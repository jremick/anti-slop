"""Baseline unit tests for the initial EV1 order ledger fixture."""

from __future__ import annotations

import unittest

from ev1_order_ledger.api import OrderService
from ev1_order_ledger.models import LineItem, Plan, ValidationError


class BaselineOrderLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.svc = OrderService()
        self.svc.register_plan(Plan(plan_id="starter", name="Starter", monthly_cents=1000, tax_bps=825))
        self.svc.register_plan(Plan(plan_id="pro", name="Pro", monthly_cents=3000, tax_bps=825))

    def test_place_order_computes_exact_integer_tax_and_records_entry(self) -> None:
        order = self.svc.place_order(
            "acct_1",
            [LineItem(sku="seat", unit_cents=1999, quantity=2)],
            tax_bps=825,
        )
        self.assertEqual(order.subtotal_cents, 3998)
        self.assertEqual(order.tax_cents, 330)  # 3998 * 825 / 10000 = 329.835 -> 330
        self.assertEqual(order.total_cents, 4328)
        stmt = self.svc.get_statement("acct_1")
        self.assertEqual(stmt["balance_cents"], 4328)
        self.assertEqual(stmt["entry_count"], 1)

    def test_legacy_flat_fee_adds_500_cents_before_tax(self) -> None:
        order = self.svc.place_order(
            "acct_1",
            [LineItem(sku="seat", unit_cents=1000, quantity=1)],
            tax_bps=1000,
            legacy_flat_fee=True,
        )
        self.assertEqual(order.subtotal_cents, 1500)
        self.assertEqual(order.tax_cents, 150)
        self.assertEqual(order.total_cents, 1650)

    def test_invalid_order_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            self.svc.place_order("", [LineItem(sku="x", unit_cents=100, quantity=1)])
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_1", [])
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_1", [LineItem(sku="x", unit_cents=0, quantity=1)])

    def test_start_subscription_validates_plan(self) -> None:
        sub = self.svc.start_subscription("acct_1", "starter")
        self.assertEqual(sub.plan_id, "starter")
        with self.assertRaises(ValidationError):
            self.svc.start_subscription("acct_1", "nonexistent")


if __name__ == "__main__":
    unittest.main()
