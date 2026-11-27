"""Visible webhook handler unit tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_PKG_DIR = Path(__file__).resolve().parents[1]
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

from models import Subscription, WebhookError, WebhookEvent  # noqa: E402
from webhooks import WebhookProcessor, compute_fee_cents  # noqa: E402


class WebhookVisibleTests(unittest.TestCase):
    def test_invoice_paid_updates_status_balance_and_fee(self) -> None:
        proc = WebhookProcessor()
        proc.register_subscription(
            Subscription("sub_1", "acct_1", status="past_due", balance_due_cents=5000, failed_attempts=2)
        )
        res = proc.handle_event(
            WebhookEvent(
                event_id="evt_paid_1",
                event_type="invoice.paid",
                subscription_id="sub_1",
                created_at=100,
                amount_cents=2000,
                fee_bps=300,
            )
        )
        self.assertTrue(res["applied"])
        self.assertEqual(res["reason"], "applied")
        self.assertEqual(res["fee_cents"], 60)
        self.assertEqual(res["subscription_status"], "active")
        self.assertEqual(res["balance_due_cents"], 3000)
        self.assertEqual(res["failed_attempts"], 0)
        self.assertEqual(compute_fee_cents(1000, 300), 30)

    def test_subscription_canceled_is_idempotent(self) -> None:
        proc = WebhookProcessor()
        proc.register_subscription(Subscription("sub_2", "acct_2", status="active"))
        ev = WebhookEvent(
            event_id="evt_cancel_1",
            event_type="subscription.canceled",
            subscription_id="sub_2",
            created_at=100,
        )
        first = proc.handle_event(ev)
        second = proc.handle_event(ev)
        self.assertTrue(first["applied"])
        self.assertEqual(first["subscription_status"], "canceled")
        self.assertFalse(second["applied"])
        self.assertEqual(second["reason"], "duplicate")

    def test_invoice_paid_idempotent_retry(self) -> None:
        proc = WebhookProcessor()
        proc.register_subscription(
            Subscription("sub_3", "acct_3", status="past_due", balance_due_cents=5000, failed_attempts=1)
        )
        ev = WebhookEvent(
            event_id="evt_paid_retry",
            event_type="invoice.paid",
            subscription_id="sub_3",
            created_at=100,
            amount_cents=2000,
            fee_bps=0,
        )
        first = proc.handle_event(ev)
        second = proc.handle_event(ev)
        self.assertTrue(first["applied"])
        self.assertEqual(first["balance_due_cents"], 3000)
        self.assertFalse(second["applied"])
        self.assertEqual(second["reason"], "duplicate")
        self.assertEqual(second["balance_due_cents"], 3000)

    def test_invoice_payment_failed_updates_balance_and_retries_idempotently(self) -> None:
        proc = WebhookProcessor()
        proc.register_subscription(
            Subscription("sub_4", "acct_4", status="active", balance_due_cents=0, failed_attempts=0)
        )
        ev = WebhookEvent(
            event_id="evt_fail_1",
            event_type="invoice.payment_failed",
            subscription_id="sub_4",
            created_at=100,
            amount_cents=1000,
            fee_bps=300,
        )
        first = proc.handle_event(ev)
        self.assertTrue(first["applied"])
        self.assertEqual(first["reason"], "applied")
        self.assertEqual(first["fee_cents"], 30)
        self.assertEqual(first["subscription_status"], "past_due")
        self.assertEqual(first["balance_due_cents"], 1030)
        self.assertEqual(first["failed_attempts"], 1)

        retry = proc.handle_event(ev)
        self.assertFalse(retry["applied"])
        self.assertEqual(retry["reason"], "duplicate")
        self.assertEqual(retry["balance_due_cents"], 1030)
        self.assertEqual(retry["failed_attempts"], 1)

    def test_unknown_event_type_raises(self) -> None:
        proc = WebhookProcessor()
        proc.register_subscription(Subscription("sub_5", "acct_5"))
        with self.assertRaises(WebhookError):
            proc.handle_event(
                WebhookEvent(
                    event_id="evt_unknown",
                    event_type="customer.created",
                    subscription_id="sub_5",
                    created_at=100,
                )
            )


if __name__ == "__main__":
    unittest.main()
