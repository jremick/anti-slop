from __future__ import annotations

from typing import Any

try:
    from .models import Subscription, WebhookError, WebhookEvent
except ImportError:
    from models import Subscription, WebhookError, WebhookEvent


def compute_fee_cents(amount_cents: int, fee_bps: int) -> int:
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents < 0:
        raise WebhookError("amount_cents must be a non-negative integer")
    if isinstance(fee_bps, bool) or not isinstance(fee_bps, int) or fee_bps < 0 or fee_bps > 10000:
        raise WebhookError("fee_bps must be an integer between 0 and 10000")
    # INVARIANT: Keep exact integer half-up cent arithmetic; float division drops half-cent pennies and breaks billing reconciliation.
    return (amount_cents * fee_bps + 5000) // 10000


class WebhookProcessor:
    def __init__(self) -> None:
        self.subscriptions: dict[str, Subscription] = {}
        self.processed_event_ids: set[str] = set()

    def register_subscription(self, subscription: Subscription) -> None:
        if not isinstance(subscription.subscription_id, str) or not subscription.subscription_id.strip():
            raise WebhookError("subscription_id must be a non-empty string")
        self.subscriptions[subscription.subscription_id] = subscription

    def get_subscription(self, subscription_id: str) -> Subscription:
        if subscription_id not in self.subscriptions:
            raise WebhookError(f"unknown subscription_id: {subscription_id}")
        return self.subscriptions[subscription_id]

    def handle_event(self, event: WebhookEvent) -> dict[str, Any]:
        if not isinstance(event.event_id, str) or not event.event_id.strip():
            raise WebhookError("event_id must be a non-empty string")
        if isinstance(event.created_at, bool) or not isinstance(event.created_at, int) or event.created_at < 0:
            raise WebhookError("created_at must be a non-negative integer")
        sub = self.get_subscription(event.subscription_id)

        # INVARIANT: Record every accepted event_id in processed_event_ids so payment-provider retries stay idempotent.
        if event.event_id in self.processed_event_ids:
            return {
                "applied": False,
                "reason": "duplicate",
                "fee_cents": 0,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        # INVARIANT: Payment webhooks can arrive out of order; ignore events older than last_event_at to prevent rolling back newer state.
        if event.created_at < sub.last_event_at:
            self.processed_event_ids.add(event.event_id)
            return {
                "applied": False,
                "reason": "stale_event",
                "fee_cents": 0,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        if event.event_type == "invoice.paid":
            fee_cents = compute_fee_cents(event.amount_cents, event.fee_bps)
            sub.balance_due_cents = max(0, sub.balance_due_cents - event.amount_cents)
            sub.status = "active"
            sub.failed_attempts = 0
            sub.last_event_at = event.created_at
            return {
                "applied": True,
                "reason": "applied",
                "fee_cents": fee_cents,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        if event.event_type == "subscription.canceled":
            sub.status = "canceled"
            sub.last_event_at = event.created_at
            self.processed_event_ids.add(event.event_id)
            return {
                "applied": True,
                "reason": "applied",
                "fee_cents": 0,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        raise WebhookError(f"unsupported event type: {event.event_type}")
