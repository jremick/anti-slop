"""Data models and constants for the billing webhook sync service."""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_CURRENCIES: frozenset[str] = frozenset(
    {"USD", "EUR", "GBP", "CAD", "AUD", "JPY"}
)

SUPPORTED_EVENT_TYPES: frozenset[str] = frozenset(
    {"charge.succeeded", "refund.succeeded"}
)


@dataclass(frozen=True)
class WebhookEvent:
    """Validated immutable billing webhook event."""

    event_id: str
    account_id: str
    amount_cents: int
    currency: str
    event_type: str


@dataclass(frozen=True)
class BatchResult:
    """Summary counts for a single call to `BillingSyncService.apply_batch`."""

    processed: int
    duplicates_skipped: int
