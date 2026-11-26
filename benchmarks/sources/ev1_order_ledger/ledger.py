"""In-memory order, subscription, and ledger store for EV1."""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import LedgerEntry, Order, Plan, Subscription, ValidationError


class OrderLedger:
    def __init__(self) -> None:
        self._plans: Dict[str, Plan] = {}
        self._orders: Dict[str, Order] = {}
        self._subscriptions: Dict[str, Subscription] = {}
        self._entries: Dict[str, LedgerEntry] = {}
        self._entry_order: List[str] = []
        self._seq = 0

    def next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:04d}"

    def add_plan(self, plan: Plan) -> None:
        if not plan.plan_id.strip():
            raise ValidationError("plan_id must be non-empty")
        if isinstance(plan.monthly_cents, bool) or not isinstance(plan.monthly_cents, int) or plan.monthly_cents < 0:
            raise ValidationError("monthly_cents must be a non-negative integer")
        self._plans[plan.plan_id] = plan

    def get_plan(self, plan_id: str) -> Plan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ValidationError(f"Unknown plan_id: {plan_id}")
        return plan

    def save_order(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise ValidationError(f"Unknown order_id: {order_id}")
        return order

    def save_subscription(self, sub: Subscription) -> None:
        self._subscriptions[sub.subscription_id] = sub

    def get_subscription(self, subscription_id: str) -> Subscription:
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise ValidationError(f"Unknown subscription_id: {subscription_id}")
        return sub

    def record_entry(self, entry: LedgerEntry) -> None:
        self._entries[entry.entry_id] = entry
        self._entry_order.append(entry.entry_id)

    def get_entry(self, entry_id: str) -> Optional[LedgerEntry]:
        return self._entries.get(entry_id)

    def entries_for_account(self, account_id: str) -> List[LedgerEntry]:
        return [
            self._entries[eid]
            for eid in self._entry_order
            if self._entries[eid].account_id == account_id
        ]

    def account_balance_cents(self, account_id: str) -> int:
        return sum(e.total_cents for e in self.entries_for_account(account_id))
