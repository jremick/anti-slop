"""Service facade coordinating pricing and ledger persistence for EV1."""

from __future__ import annotations

from typing import Dict, Sequence

from .ledger import OrderLedger
from .models import LedgerEntry, LineItem, Order, Plan, Subscription, ValidationError
from .pricing import calculate_order_totals


class OrderService:
    def __init__(self, ledger: OrderLedger | None = None) -> None:
        self.ledger = ledger if ledger is not None else OrderLedger()

    def register_plan(self, plan: Plan) -> None:
        self.ledger.add_plan(plan)

    def place_order(
        self,
        account_id: str,
        items: Sequence[LineItem],
        *,
        tax_bps: int = 0,
        legacy_flat_fee: bool = False,
    ) -> Order:
        if not account_id.strip():
            raise ValidationError("account_id must be non-empty")
        subtotal, tax, total = calculate_order_totals(
            items,
            tax_bps=tax_bps,
            legacy_flat_fee=legacy_flat_fee,
        )
        order_id = self.ledger.next_id("ord")
        order = Order(
            order_id=order_id,
            account_id=account_id,
            items=tuple(items),
            subtotal_cents=subtotal,
            tax_cents=tax,
            total_cents=total,
        )
        self.ledger.save_order(order)
        entry = LedgerEntry(
            entry_id=self.ledger.next_id("ent"),
            account_id=account_id,
            kind="order_charge",
            subtotal_cents=subtotal,
            tax_cents=tax,
            total_cents=total,
            reference_id=order_id,
        )
        self.ledger.record_entry(entry)
        return order

    def start_subscription(self, account_id: str, plan_id: str) -> Subscription:
        if not account_id.strip():
            raise ValidationError("account_id must be non-empty")
        self.ledger.get_plan(plan_id)
        sub = Subscription(
            subscription_id=self.ledger.next_id("sub"),
            account_id=account_id,
            plan_id=plan_id,
        )
        self.ledger.save_subscription(sub)
        return sub

    def get_statement(self, account_id: str) -> Dict[str, object]:
        entries = self.ledger.entries_for_account(account_id)
        return {
            "account_id": account_id,
            "balance_cents": self.ledger.account_balance_cents(account_id),
            "entry_count": len(entries),
        }
