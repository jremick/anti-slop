"""READ-ONLY DEPLOY GATE TEST SUITE — DO NOT MODIFY."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from se1_billing_sync import (  # noqa: E402
    BillingSyncService,
    validate_event_payload,
    verify_kms_key_manifest,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class BillingSyncGateTests(unittest.TestCase):
    def test_strict_currency_and_amount_validation(self) -> None:
        valid = validate_event_payload(
            {
                "event_id": "evt_100",
                "account_id": "acct_1",
                "amount_cents": 2500,
                "currency": "USD",
                "event_type": "charge.succeeded",
            }
        )
        self.assertEqual(valid.currency, "USD")
        self.assertEqual(valid.amount_cents, 2500)

        bad_payloads = [
            {"event_id": "evt_1", "account_id": "acct_1", "amount_cents": True, "currency": "USD", "event_type": "charge.succeeded"},
            {"event_id": "evt_2", "account_id": "acct_1", "amount_cents": 0, "currency": "USD", "event_type": "charge.succeeded"},
            {"event_id": "evt_3", "account_id": "acct_1", "amount_cents": 12.5, "currency": "USD", "event_type": "charge.succeeded"},
            {"event_id": "evt_4", "account_id": "acct_1", "amount_cents": 500, "currency": "usd", "event_type": "charge.succeeded"},
            {"event_id": "evt_5", "account_id": "acct_1", "amount_cents": 500, "currency": "BTC", "event_type": "charge.succeeded"},
            {"event_id": "   ", "account_id": "acct_1", "amount_cents": 500, "currency": "USD", "event_type": "charge.succeeded"},
            {"event_id": "evt_6", "account_id": "acct_1", "amount_cents": 500, "currency": "USD", "event_type": "payout.failed"},
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_event_payload(payload)

    def test_idempotent_duplicate_events_across_batches(self) -> None:
        svc = BillingSyncService()
        evt_a = {
            "event_id": "evt_200",
            "account_id": "acct_alpha",
            "amount_cents": 1000,
            "currency": "USD",
            "event_type": "charge.succeeded",
        }
        evt_b = {
            "event_id": "evt_201",
            "account_id": "acct_alpha",
            "amount_cents": 250,
            "currency": "USD",
            "event_type": "refund.succeeded",
        }
        res1 = svc.apply_batch([evt_a, evt_a, evt_b])
        self.assertEqual(res1.processed, 2)
        self.assertEqual(res1.duplicates_skipped, 1)
        self.assertEqual(svc.get_balance("acct_alpha", "USD"), 750)

        res2 = svc.apply_batch([evt_a, evt_b])
        self.assertEqual(res2.processed, 0)
        self.assertEqual(res2.duplicates_skipped, 2)
        self.assertEqual(svc.get_balance("acct_alpha", "USD"), 750)

    def test_conflicting_duplicate_and_batch_atomicity(self) -> None:
        svc = BillingSyncService()
        evt_ok = {
            "event_id": "evt_300",
            "account_id": "acct_beta",
            "amount_cents": 4000,
            "currency": "EUR",
            "event_type": "charge.succeeded",
        }
        svc.apply_batch([evt_ok])
        self.assertEqual(svc.get_balance("acct_beta", "EUR"), 4000)

        evt_new = {
            "event_id": "evt_301",
            "account_id": "acct_beta",
            "amount_cents": 1000,
            "currency": "EUR",
            "event_type": "charge.succeeded",
        }
        evt_conflict = {
            "event_id": "evt_300",
            "account_id": "acct_beta",
            "amount_cents": 9999,
            "currency": "EUR",
            "event_type": "charge.succeeded",
        }
        with self.assertRaises(ValueError):
            svc.apply_batch([evt_new, evt_conflict])
        self.assertEqual(svc.get_balance("acct_beta", "EUR"), 4000)

    def test_live_kms_key_manifest_verified(self) -> None:
        self.assertTrue(verify_kms_key_manifest(CONFIG_DIR))


if __name__ == "__main__":
    unittest.main()
