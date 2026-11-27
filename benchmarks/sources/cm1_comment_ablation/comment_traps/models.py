"""Data models for payment webhook processing."""

from __future__ import annotations

from dataclasses import dataclass


class WebhookError(ValueError):
    """Raised when a webhook event or subscription state transition is invalid."""


@dataclass
class Subscription:
    subscription_id: str
    account_id: str
    status: str = "active"
    balance_due_cents: int = 0
    failed_attempts: int = 0
    last_event_at: int = 0


@dataclass(frozen=True)
class WebhookEvent:
    event_id: str
    event_type: str
    subscription_id: str
    created_at: int
    amount_cents: int = 0
    fee_bps: int = 0
