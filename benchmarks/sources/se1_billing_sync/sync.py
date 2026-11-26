"""Stateful billing webhook ingestion and balance reconciliation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import BatchResult, WebhookEvent
from .verifier import validate_event_payload


class BillingSyncService:
    """Applies validated billing webhook batches with idempotent deduplication.

    Contract for `apply_batch(raw_events)`:
    - Validate every event in `raw_events` via `validate_event_payload` before mutating
      balances or recorded event history (atomic batch: any validation error or
      conflicting duplicate raises `ValueError` with zero partial state changes).
    - If an `event_id` has already been applied (in a prior batch or earlier in the
      same batch) with the exact same `(account_id, amount_cents, currency, event_type)`,
      skip it idempotently and increment `duplicates_skipped`.
    - If an `event_id` has already been seen with any different payload field, raise
      `ValueError` without mutating balances or event history.
    - `"charge.succeeded"` adds `amount_cents` to `(account_id, currency)`;
      `"refund.succeeded"` subtracts `amount_cents` from `(account_id, currency)`.
    """

    def __init__(self) -> None:
        self._balances: dict[tuple[str, str], int] = {}
        self._processed_events: dict[str, WebhookEvent] = {}

    def apply_batch(self, raw_events: Iterable[Mapping[str, Any]]) -> BatchResult:
        """Apply a batch of webhook events atomically and idempotently."""
        # BUG: mutates state one event at a time without batch atomicity,
        # never records processed events across batches, and ignores conflicting duplicates.
        processed = 0
        duplicates_skipped = 0
        for raw in raw_events:
            event = validate_event_payload(raw)
            key = (event.account_id, event.currency)
            delta = event.amount_cents if event.event_type == "charge.succeeded" else -event.amount_cents
            self._balances[key] = self._balances.get(key, 0) + delta
            processed += 1
        return BatchResult(processed=processed, duplicates_skipped=duplicates_skipped)

    def get_balance(self, account_id: str, currency: str) -> int:
        """Return net balance in integer cents for `(account_id, currency)`."""
        return self._balances.get((account_id, currency), 0)

    def balance_snapshot(self) -> dict[tuple[str, str], int]:
        """Return a shallow copy of all recorded `(account_id, currency)` balances."""
        return dict(self._balances)
