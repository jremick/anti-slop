"""Stdlib-only tests for Pillar 3: EV1 multi-turn evolution benchmark, AST mutation
testing engine (benchmarks/evolution.py), and grade_ev1.py compounding quality grader.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks import evolution  # noqa: E402
from benchmarks.graders import grade_ev1  # noqa: E402
from scripts import benchmark  # noqa: E402


FIXTURE_DIR = REPO_ROOT / "benchmarks/sources/ev1_order_ledger"


CLEAN_MODELS_PY = '''"""Core domain models for the EV1 order ledger fixture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


class BillingError(Exception):
    """Base error for billing domain failures."""


class ValidationError(BillingError):
    """Raised when input arguments or business invariants are violated."""


@dataclass(frozen=True)
class Plan:
    plan_id: str
    name: str
    monthly_cents: int
    tax_bps: int = 0


@dataclass(frozen=True)
class PromoCode:
    code: str
    percent_off: int | None = None
    amount_off_cents: int | None = None
    expires_on: str | None = None
    min_subtotal_cents: int = 0


@dataclass(frozen=True)
class LineItem:
    sku: str
    unit_cents: int
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: str
    account_id: str
    items: Tuple[LineItem, ...]
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    discount_cents: int = 0
    promo_code: str | None = None


@dataclass
class Subscription:
    subscription_id: str
    account_id: str
    plan_id: str
    status: str = "active"


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    account_id: str
    kind: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    reference_id: str
    reason: str = ""
    metadata: dict = field(default_factory=dict)
'''

CLEAN_PRICING_PY = '''"""Canonical integer-cent pricing calculations for EV1 order ledger."""

from __future__ import annotations

from typing import Sequence, Tuple

from .models import LineItem, Plan, PromoCode, ValidationError


def validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field_name} must be a non-negative integer")
    return value


def validate_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{field_name} must be a positive integer")
    return value


def round_half_up_div(numerator: int, denominator: int) -> int:
    """Exact integer half-up division for non-negative numerator and positive denominator."""
    validate_non_negative_int(numerator, "numerator")
    validate_positive_int(denominator, "denominator")
    return (numerator * 2 + denominator) // (2 * denominator)


def compute_subtotal_cents(items: Sequence[LineItem]) -> int:
    if not items:
        raise ValidationError("items must be non-empty")
    subtotal = 0
    for item in items:
        validate_positive_int(item.unit_cents, "unit_cents")
        validate_positive_int(item.quantity, "quantity")
        subtotal += item.unit_cents * item.quantity
    return subtotal


def compute_tax_cents(taxable_cents: int, tax_bps: int) -> int:
    validate_non_negative_int(taxable_cents, "taxable_cents")
    validate_non_negative_int(tax_bps, "tax_bps")
    if tax_bps > 10_000:
        raise ValidationError("tax_bps cannot exceed 10000")
    return round_half_up_div(taxable_cents * tax_bps, 10_000)


def compute_prorated_upgrade_cents(
    old_plan: Plan,
    new_plan: Plan,
    days_remaining: int,
    cycle_days: int,
) -> int:
    validate_positive_int(cycle_days, "cycle_days")
    validate_non_negative_int(days_remaining, "days_remaining")
    if days_remaining > cycle_days:
        raise ValidationError("days_remaining cannot exceed cycle_days")
    if new_plan.monthly_cents <= old_plan.monthly_cents:
        raise ValidationError("new_plan must be strictly more expensive than old_plan")
    diff = new_plan.monthly_cents - old_plan.monthly_cents
    return round_half_up_div(diff * days_remaining, cycle_days)


def apply_promo_and_tax(
    gross_subtotal: int,
    tax_bps: int,
    promo: PromoCode | None = None,
    as_of: str | None = None,
) -> Tuple[int, int, int, int]:
    """Return (discounted_subtotal, discount_cents, tax_cents, total_cents)."""
    validate_non_negative_int(gross_subtotal, "gross_subtotal")
    discount = 0
    if promo is not None:
        if promo.expires_on is not None:
            if not as_of or as_of > promo.expires_on:
                raise ValidationError(f"Promo code '{promo.code}' is expired or missing as_of date")
        if gross_subtotal < promo.min_subtotal_cents:
            raise ValidationError("Subtotal below promo minimum")
        if promo.percent_off is not None:
            discount = round_half_up_div(gross_subtotal * promo.percent_off, 100)
        elif promo.amount_off_cents is not None:
            discount = min(gross_subtotal, promo.amount_off_cents)
    discounted = gross_subtotal - discount
    tax = compute_tax_cents(discounted, tax_bps)
    return discounted, discount, tax, discounted + tax


def calculate_order_totals(
    items: Sequence[LineItem],
    *,
    tax_bps: int = 0,
    promo: PromoCode | None = None,
    as_of: str | None = None,
) -> Tuple[int, int, int, int]:
    """Return (subtotal_cents, discount_cents, tax_cents, total_cents)."""
    gross = compute_subtotal_cents(items)
    return apply_promo_and_tax(gross, tax_bps, promo=promo, as_of=as_of)


def compute_partial_refund_split(
    order_total_cents: int,
    order_tax_cents: int,
    already_refunded_total: int,
    already_refunded_tax: int,
    refund_amount_cents: int,
) -> Tuple[int, int]:
    """Return (refund_subtotal_cents, refund_tax_cents) conserving exact cumulative tax."""
    validate_positive_int(refund_amount_cents, "refund_amount_cents")
    cum_after = already_refunded_total + refund_amount_cents
    if cum_after > order_total_cents:
        raise ValidationError("Refund exceeds remaining refundable order total")
    if cum_after == order_total_cents:
        cum_tax_after = order_tax_cents
    else:
        cum_tax_after = round_half_up_div(order_tax_cents * cum_after, order_total_cents)
    refund_tax = cum_tax_after - already_refunded_tax
    return refund_amount_cents - refund_tax, refund_tax
'''

CLEAN_LEDGER_PY = '''"""In-memory order, subscription, promo, and ledger store for EV1."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .models import LedgerEntry, Order, Plan, PromoCode, Subscription, ValidationError


class OrderLedger:
    def __init__(self) -> None:
        self._plans: Dict[str, Plan] = {}
        self._promos: Dict[str, PromoCode] = {}
        self._orders: Dict[str, Order] = {}
        self._subscriptions: Dict[str, Subscription] = {}
        self._entries: Dict[str, LedgerEntry] = {}
        self._entry_order: List[str] = []
        self._idempotency: Dict[str, Tuple[Tuple[object, ...], str]] = {}
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

    def add_promo(self, promo: PromoCode) -> None:
        self._promos[promo.code] = promo

    def get_promo(self, code: str) -> PromoCode:
        if not isinstance(code, str) or not code.strip() or "," in code:
            raise ValidationError("Invalid or stacked promo code")
        promo = self._promos.get(code)
        if promo is None:
            raise ValidationError(f"Unknown promo code: {code}")
        return promo

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

    def lookup_idempotency(self, key: str, fingerprint: Tuple[object, ...]) -> Optional[LedgerEntry]:
        if not isinstance(key, str) or not key.strip():
            raise ValidationError("idempotency_key must be a non-empty string")
        existing = self._idempotency.get(key)
        if existing is None:
            return None
        saved_fp, entry_id = existing
        if saved_fp != fingerprint:
            raise ValidationError(f"Conflicting parameters for idempotency_key '{key}'")
        return self._entries[entry_id]

    def save_idempotency(self, key: str, fingerprint: Tuple[object, ...], entry_id: str) -> None:
        self._idempotency[key] = (fingerprint, entry_id)

    def refunded_totals_for_order(self, order_id: str) -> Tuple[int, int]:
        total_ref = 0
        tax_ref = 0
        for eid in self._entry_order:
            e = self._entries[eid]
            if e.kind == "order_refund" and e.reference_id == order_id:
                total_ref += -e.total_cents
                tax_ref += -e.tax_cents
        return total_ref, tax_ref

    def entries_for_account(self, account_id: str) -> List[LedgerEntry]:
        return [
            self._entries[eid]
            for eid in self._entry_order
            if self._entries[eid].account_id == account_id
        ]

    def account_balance_cents(self, account_id: str) -> int:
        return sum(e.total_cents for e in self.entries_for_account(account_id))
'''

CLEAN_API_PY = '''"""Service facade coordinating pricing, ledger persistence, and audit logging for EV1."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

from .ledger import OrderLedger
from .models import LedgerEntry, LineItem, Order, Plan, PromoCode, Subscription, ValidationError
from .pricing import (
    apply_promo_and_tax,
    calculate_order_totals,
    compute_partial_refund_split,
    compute_prorated_upgrade_cents,
    validate_non_negative_int,
    validate_positive_int,
)


class OrderService:
    def __init__(
        self,
        ledger: OrderLedger | None = None,
        audit_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.ledger = ledger if ledger is not None else OrderLedger()
        self._audit_sink = audit_sink

    def _emit_audit(self, entry: LedgerEntry) -> None:
        if self._audit_sink is not None:
            self._audit_sink({
                "action": entry.kind,
                "account_id": entry.account_id,
                "amount_cents": entry.total_cents,
                "entry_id": entry.entry_id,
            })

    def register_plan(self, plan: Plan) -> None:
        self.ledger.add_plan(plan)

    def register_promo(
        self,
        code: str,
        *,
        percent_off: int | None = None,
        amount_off_cents: int | None = None,
        expires_on: str | None = None,
        min_subtotal_cents: int = 0,
    ) -> None:
        if not isinstance(code, str) or not code.strip() or "," in code:
            raise ValidationError("code must be a single non-empty promo identifier")
        if (percent_off is None) == (amount_off_cents is None):
            raise ValidationError("Provide exactly one of percent_off or amount_off_cents")
        if percent_off is not None:
            validate_positive_int(percent_off, "percent_off")
            if percent_off > 100:
                raise ValidationError("percent_off cannot exceed 100")
        if amount_off_cents is not None:
            validate_positive_int(amount_off_cents, "amount_off_cents")
        validate_non_negative_int(min_subtotal_cents, "min_subtotal_cents")
        self.ledger.add_promo(
            PromoCode(
                code=code.strip(),
                percent_off=percent_off,
                amount_off_cents=amount_off_cents,
                expires_on=expires_on,
                min_subtotal_cents=min_subtotal_cents,
            )
        )

    def place_order(
        self,
        account_id: str,
        items: Sequence[LineItem],
        *,
        tax_bps: int = 0,
        promo_code: str | None = None,
        as_of: str | None = None,
    ) -> Order:
        if not account_id.strip():
            raise ValidationError("account_id must be non-empty")
        promo = self.ledger.get_promo(promo_code) if promo_code is not None else None
        subtotal, discount, tax, total = calculate_order_totals(
            items,
            tax_bps=tax_bps,
            promo=promo,
            as_of=as_of,
        )
        order_id = self.ledger.next_id("ord")
        order = Order(
            order_id=order_id,
            account_id=account_id,
            items=tuple(items),
            subtotal_cents=subtotal,
            tax_cents=tax,
            total_cents=total,
            discount_cents=discount,
            promo_code=promo.code if promo is not None else None,
        )
        entry = LedgerEntry(
            entry_id=self.ledger.next_id("ent"),
            account_id=account_id,
            kind="order_charge",
            subtotal_cents=subtotal,
            tax_cents=tax,
            total_cents=total,
            reference_id=order_id,
        )
        self._emit_audit(entry)
        self.ledger.save_order(order)
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

    def upgrade_subscription(
        self,
        subscription_id: str,
        new_plan_id: str,
        days_remaining: int,
        cycle_days: int,
        *,
        idempotency_key: str,
        promo_code: str | None = None,
        as_of: str | None = None,
    ) -> LedgerEntry:
        fp = ("upgrade", subscription_id, new_plan_id, days_remaining, cycle_days, promo_code, as_of)
        replay = self.ledger.lookup_idempotency(idempotency_key, fp)
        if replay is not None:
            return replay

        sub = self.ledger.get_subscription(subscription_id)
        old_plan = self.ledger.get_plan(sub.plan_id)
        new_plan = self.ledger.get_plan(new_plan_id)
        gross = compute_prorated_upgrade_cents(old_plan, new_plan, days_remaining, cycle_days)
        promo = self.ledger.get_promo(promo_code) if promo_code is not None else None
        subtotal, _discount, tax, total = apply_promo_and_tax(
            gross, new_plan.tax_bps, promo=promo, as_of=as_of
        )
        entry = LedgerEntry(
            entry_id=self.ledger.next_id("ent"),
            account_id=sub.account_id,
            kind="plan_upgrade",
            subtotal_cents=subtotal,
            tax_cents=tax,
            total_cents=total,
            reference_id=subscription_id,
        )
        self._emit_audit(entry)
        sub.plan_id = new_plan_id
        self.ledger.record_entry(entry)
        self.ledger.save_idempotency(idempotency_key, fp, entry.entry_id)
        return entry

    def refund_order(
        self,
        order_id: str,
        amount_cents: int,
        *,
        reason: str,
        idempotency_key: str,
    ) -> LedgerEntry:
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("reason must be a non-empty string")
        fp = ("refund", order_id, amount_cents, reason.strip())
        replay = self.ledger.lookup_idempotency(idempotency_key, fp)
        if replay is not None:
            return replay

        order = self.ledger.get_order(order_id)
        done_total, done_tax = self.ledger.refunded_totals_for_order(order_id)
        ref_sub, ref_tax = compute_partial_refund_split(
            order.total_cents, order.tax_cents, done_total, done_tax, amount_cents
        )
        entry = LedgerEntry(
            entry_id=self.ledger.next_id("ent"),
            account_id=order.account_id,
            kind="order_refund",
            subtotal_cents=-ref_sub,
            tax_cents=-ref_tax,
            total_cents=-amount_cents,
            reference_id=order_id,
            reason=reason.strip(),
        )
        self._emit_audit(entry)
        self.ledger.record_entry(entry)
        self.ledger.save_idempotency(idempotency_key, fp, entry.entry_id)
        return entry

    def export_credit_note(self, refund_entry_id: str) -> Dict[str, Any]:
        entry = self.ledger.get_entry(refund_entry_id)
        if entry is None or entry.kind != "order_refund":
            raise ValidationError(f"Unknown refund entry: {refund_entry_id}")
        return {
            "entry_id": entry.entry_id,
            "order_id": entry.reference_id,
            "account_id": entry.account_id,
            "subtotal_cents": -entry.subtotal_cents,
            "tax_cents": -entry.tax_cents,
            "total_cents": -entry.total_cents,
            "reason": entry.reason,
        }

    def get_statement(self, account_id: str) -> Dict[str, object]:
        entries = self.ledger.entries_for_account(account_id)
        return {
            "account_id": account_id,
            "balance_cents": self.ledger.account_balance_cents(account_id),
            "entry_count": len(entries),
        }
'''

CLEAN_TESTS_PY = '''"""Comprehensive unit tests covering Turns 1-4 of EV1 order ledger."""

from __future__ import annotations

import unittest

from ev1_order_ledger.api import OrderService
from ev1_order_ledger.models import LineItem, Plan, ValidationError
from ev1_order_ledger.pricing import calculate_order_totals, compute_tax_cents, round_half_up_div


class CleanEvolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = []
        self.svc = OrderService(audit_sink=self.events.append)
        self.svc.register_plan(Plan(plan_id="starter", name="Starter", monthly_cents=1000, tax_bps=825))
        self.svc.register_plan(Plan(plan_id="pro", name="Pro", monthly_cents=3000, tax_bps=825))
        self.svc.register_plan(Plan(plan_id="scale", name="Scale", monthly_cents=5001, tax_bps=1000))

    def test_order_math_rounding_and_validation(self) -> None:
        self.assertEqual(round_half_up_div(5, 2), 3)
        self.assertEqual(compute_tax_cents(1000, 10000), 1000)
        with self.assertRaises(ValidationError):
            compute_tax_cents(1000, 10001)
        order = self.svc.place_order("acct_1", [LineItem("seat", 1999, 2)], tax_bps=825)
        self.assertEqual((order.subtotal_cents, order.tax_cents, order.total_cents), (3998, 330, 4328))
        self.assertEqual(self.svc.get_statement("acct_1")["balance_cents"], 4328)
        with self.assertRaises(ValidationError):
            self.svc.place_order("", [LineItem("seat", 100, 1)])
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_1", [])
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_1", [LineItem("seat", 0, 1)])
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_1", [LineItem("seat", 100, 0)])
        with self.assertRaises(ValidationError):
            self.svc.register_plan(Plan("", "Bad", 100))
        with self.assertRaises(ValidationError):
            self.svc.register_plan(Plan("neg", "Neg", -1))
        # Boundary: free ($0) plan is valid.
        self.svc.register_plan(Plan("free", "Free", 0, tax_bps=0))
        self.assertEqual(self.svc.ledger.get_plan("free").monthly_cents, 0)

    def test_prorated_upgrades_and_idempotency(self) -> None:
        sub = self.svc.start_subscription("acct_1", "starter")
        e1 = self.svc.upgrade_subscription(sub.subscription_id, "pro", 15, 30, idempotency_key="u1")
        self.assertEqual((e1.subtotal_cents, e1.tax_cents, e1.total_cents), (1000, 83, 1083))
        self.assertEqual(self.svc.ledger.get_subscription(sub.subscription_id).plan_id, "pro")
        # Exact boundary: days_remaining == cycle_days (full cycle upgrade).
        sub_full = self.svc.start_subscription("acct_1", "starter")
        e_full = self.svc.upgrade_subscription(sub_full.subscription_id, "pro", 30, 30, idempotency_key="u-full")
        self.assertEqual(e_full.subtotal_cents, 2000)
        # Exact boundary: days_remaining == 0 (0-cent upgrade).
        sub_zero = self.svc.start_subscription("acct_1", "starter")
        e_zero = self.svc.upgrade_subscription(sub_zero.subscription_id, "pro", 0, 30, idempotency_key="u-zero-days")
        self.assertEqual(e_zero.total_cents, 0)
        replay = self.svc.upgrade_subscription(sub.subscription_id, "pro", 15, 30, idempotency_key="u1")
        self.assertEqual(replay.entry_id, e1.entry_id)
        self.assertEqual(len(self.events), 3)
        with self.assertRaises(ValidationError):
            self.svc.upgrade_subscription(sub.subscription_id, "scale", 10, 30, idempotency_key="u1")
        with self.assertRaises(ValidationError):
            self.svc.upgrade_subscription(sub.subscription_id, "starter", 10, 30, idempotency_key="u-down")
        with self.assertRaises(ValidationError):
            self.svc.upgrade_subscription(sub.subscription_id, "scale", 31, 30, idempotency_key="u-hi")
        with self.assertRaises(ValidationError):
            self.svc.upgrade_subscription(sub.subscription_id, "scale", -1, 30, idempotency_key="u-lo")
        with self.assertRaises(ValidationError):
            self.svc.upgrade_subscription(sub.subscription_id, "scale", 5, 0, idempotency_key="u-zero")
        with self.assertRaises(ValidationError):
            self.svc.upgrade_subscription(sub.subscription_id, "scale", 5, 30, idempotency_key="")
        e2 = self.svc.upgrade_subscription(sub.subscription_id, "scale", 1, 2, idempotency_key="u2")
        self.assertEqual(e2.subtotal_cents, 1001)

    def test_promos_orders_upgrades_and_validation(self) -> None:
        self.svc.register_promo("SAVE20", percent_off=20, expires_on="2026-12-31", min_subtotal_cents=1000)
        self.svc.register_promo("FLAT500", amount_off_cents=500, expires_on="2026-11-01")
        with self.assertRaises(ValidationError):
            self.svc.register_promo("BAD", percent_off=10, amount_off_cents=100)
        with self.assertRaises(ValidationError):
            self.svc.register_promo("BAD2", percent_off=101)
        o = self.svc.place_order("acct_p", [LineItem("sku", 2500, 1)], tax_bps=1000, promo_code="SAVE20", as_of="2026-12-31")
        self.assertEqual((o.subtotal_cents, o.discount_cents, o.tax_cents, o.total_cents), (2000, 500, 200, 2200))
        o_flat = self.svc.place_order("acct_p", [LineItem("sku", 1000, 1)], tax_bps=0, promo_code="FLAT500", as_of="2026-11-01")
        self.assertEqual((o_flat.subtotal_cents, o_flat.discount_cents), (500, 500))
        sub = self.svc.start_subscription("acct_p", "starter")
        eu = self.svc.upgrade_subscription(sub.subscription_id, "pro", 15, 30, idempotency_key="up", promo_code="SAVE20", as_of="2026-11-20")
        self.assertEqual((eu.subtotal_cents, eu.tax_cents, eu.total_cents), (800, 66, 866))
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_p", [LineItem("sku", 2000, 1)], promo_code="FLAT500", as_of="2026-11-02")
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_p", [LineItem("sku", 2000, 1)], promo_code="SAVE20")
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_p", [LineItem("sku", 2000, 1)], promo_code="SAVE20,FLAT500", as_of="2026-10-01")
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_p", [LineItem("sku", 500, 1)], promo_code="SAVE20", as_of="2026-11-20")
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_p", [LineItem("sku", 2000, 1)], promo_code="MISSING", as_of="2026-11-20")
        with self.assertRaises(ValidationError):
            self.svc.place_order("acct_p", [LineItem("sku", 2000, 1)], promo_code="   ", as_of="2026-11-20")
        with self.assertRaises(ValidationError):
            self.svc.register_promo("   ", percent_off=10)
        with self.assertRaises(ValidationError):
            self.svc.register_promo("NEGMIN", percent_off=10, min_subtotal_cents=-1)
        with self.assertRaises(ValidationError):
            self.svc.start_subscription("acct_p", "no-such-plan")
        with self.assertRaises(ValidationError):
            self.svc.refund_order("ord_missing", 10, reason="x", idempotency_key="r-miss")

    def test_partial_refunds_credit_notes_legacy_removal_and_fail_closed_audit(self) -> None:
        o = self.svc.place_order("acct_r", [LineItem("sku", 1000, 1)], tax_bps=825)
        r1 = self.svc.refund_order(o.order_id, 361, reason="part 1", idempotency_key="r1")
        r2 = self.svc.refund_order(o.order_id, 361, reason="part 2", idempotency_key="r2")
        r3 = self.svc.refund_order(o.order_id, 361, reason="part 3", idempotency_key="r3")
        self.assertEqual(-(r1.tax_cents + r2.tax_cents + r3.tax_cents), o.tax_cents)
        self.assertEqual(self.svc.ledger.account_balance_cents("acct_r"), 0)
        self.assertEqual(self.svc.refund_order(o.order_id, 361, reason="part 1", idempotency_key="r1").entry_id, r1.entry_id)
        with self.assertRaises(ValidationError):
            self.svc.refund_order(o.order_id, 1, reason="over", idempotency_key="r-over")
        with self.assertRaises(ValidationError):
            self.svc.refund_order(o.order_id, 100, reason="part 1", idempotency_key="r1")
        with self.assertRaises(ValidationError):
            self.svc.refund_order(o.order_id, 100, reason="", idempotency_key="r-noreason")
        cn = self.svc.export_credit_note(r1.entry_id)
        self.assertEqual(cn["total_cents"], 361)
        self.assertEqual(cn["subtotal_cents"] + cn["tax_cents"], 361)
        with self.assertRaises(ValidationError):
            self.svc.export_credit_note("ent_9999")
        with self.assertRaises(TypeError):
            calculate_order_totals([LineItem("x", 100, 1)], legacy_flat_fee=True)  # type: ignore[call-arg]  # verify removed arg
        with self.assertRaises(TypeError):
            self.svc.place_order("acct_r", [LineItem("x", 100, 1)], legacy_flat_fee=True)  # type: ignore[call-arg]  # verify removed arg

        def boom(_ev):
            raise RuntimeError("audit down")

        svc_fail = OrderService(audit_sink=boom)
        with self.assertRaises(RuntimeError):
            svc_fail.place_order("acct_fail", [LineItem("x", 100, 1)])
        self.assertEqual(svc_fail.ledger.entries_for_account("acct_fail"), [])


if __name__ == "__main__":
    unittest.main()
'''


class EvolutionBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _copy_fixture(self) -> Path:
        dst = self.root / "ev1_order_ledger"
        shutil.copytree(FIXTURE_DIR, dst)
        return dst

    def test_ev1_case_and_planned_pilot_manifest_validate_cleanly(self) -> None:
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks/cases", REPO_ROOT)
        self.assertIn(("EV1", "0.7.0"), cases)
        pilot = benchmark.read_json(REPO_ROOT / "benchmarks/pilot-evolution-v0.7.0.json")
        validated = benchmark.validate_pilot(pilot, cases, "benchmarks/pilot-evolution-v0.7.0.json")
        self.assertEqual(validated["status"], "planned")
        self.assertEqual(validated["experiment_id"], "pilot-evolution-v0.7.0")

    def test_unpatched_fixture_fails_stage4_grader_cleanly(self) -> None:
        ws = self._copy_fixture()
        report = grade_ev1.grade(ws, stage=4, max_mutants=12)
        self.assertFalse(report["passed"])
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertFalse(by_id["functional_all_turns"]["passed"])
        self.assertFalse(by_id["no_dead_or_legacy_code"]["passed"])

    def test_clean_reference_4turn_implementation_passes_all_six_checks_and_mutation_testing(self) -> None:
        ws = self._copy_fixture()
        (ws / "models.py").write_text(CLEAN_MODELS_PY, encoding="utf-8")
        (ws / "pricing.py").write_text(CLEAN_PRICING_PY, encoding="utf-8")
        (ws / "ledger.py").write_text(CLEAN_LEDGER_PY, encoding="utf-8")
        (ws / "api.py").write_text(CLEAN_API_PY, encoding="utf-8")
        (ws / "tests/test_orders.py").write_text(CLEAN_TESTS_PY, encoding="utf-8")

        report = grade_ev1.grade(ws, stage=4, max_mutants=18)
        self.assertTrue(report["passed"], msg=json.dumps(report, indent=2))
        self.assertGreaterEqual(report["metrics"]["mutation_kill_rate"], 0.65)
        self.assertEqual(report["metrics"]["duplicate_blocks"], 0)
        self.assertEqual(report["metrics"]["dead_compat"], 0)
        self.assertEqual(report["metrics"]["silent_failures_and_shortcuts"], 0)

    def test_slop_implementation_is_caught_on_mutation_duplicates_dead_code_and_silent_fallbacks(self) -> None:
        ws = self._copy_fixture()
        (ws / "models.py").write_text(CLEAN_MODELS_PY, encoding="utf-8")
        (ws / "pricing.py").write_text(CLEAN_PRICING_PY, encoding="utf-8")
        (ws / "ledger.py").write_text(CLEAN_LEDGER_PY, encoding="utf-8")

        # Inject convincing-looking AI slop into api.py:
        # 1) Copy-pasted pricing block from pricing.py (`apply_promo_and_tax` clone with renamed vars)
        # 2) Leftover unreferenced legacy helper + legacy_flat_fee reference
        # 3) Broad silent fallback returning 0
        slop_extra = (
            "\n\ndef _duplicated_promo_calc(base_amt, rate_bps, coupon=None, date_str=None):\n"
            "    validate_non_negative_int(base_amt, 'base_amt')\n"
            "    disc = 0\n"
            "    if coupon is not None:\n"
            "        if coupon.expires_on is not None:\n"
            "            if not date_str or date_str > coupon.expires_on:\n"
            "                raise ValidationError('expired')\n"
            "        if base_amt < coupon.min_subtotal_cents:\n"
            "            raise ValidationError('below min')\n"
            "        if coupon.percent_off is not None:\n"
            "            disc = round_half_up_div(base_amt * coupon.percent_off, 100)\n"
            "        elif coupon.amount_off_cents is not None:\n"
            "            disc = min(base_amt, coupon.amount_off_cents)\n"
            "    net = base_amt - disc\n"
            "    tax_amt = compute_tax_cents(net, rate_bps)\n"
            "    return net, disc, tax_amt, net + tax_amt\n\n"
            "def legacy_flat_fee_helper(x):\n"
            "    try:\n"
            "        return int(x)\n"
            "    except Exception:\n"
            "        return 0\n"
        )
        (ws / "api.py").write_text(
            CLEAN_API_PY.replace("    validate_positive_int,\n)", "    validate_positive_int,\n    compute_tax_cents,\n    round_half_up_div,\n)")
            + slop_extra,
            encoding="utf-8",
        )
        # Replace real tests with weak test theater that passes on clean code AND survives mutations!
        (ws / "tests/test_orders.py").write_text(
            "import unittest\n"
            "from ev1_order_ledger.api import OrderService\n\n"
            "class WeakTheaterTests(unittest.TestCase):\n"
            "    def test_service_initializes(self):\n"
            "        OrderService()\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )

        report = grade_ev1.grade(ws, stage=4, max_mutants=12)
        self.assertFalse(report["passed"])
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertFalse(by_id["mutation_test_strength"]["passed"])
        self.assertFalse(by_id["no_duplicate_code_growth"]["passed"])
        self.assertFalse(by_id["no_dead_or_legacy_code"]["passed"])
        self.assertFalse(by_id["no_silent_failures_or_shortcuts"]["passed"])

    def test_compare_evolution_arms_returns_keep_drop_and_inconclusive(self) -> None:
        base = [
            {
                "functional_passed": True,
                "mutation_kill_rate": 0.45,
                "duplicate_blocks": 2,
                "dead_compat": 1,
                "god_functions": 1,
                "silent_failures_and_shortcuts": 1,
                "test_theater": 1,
            }
        ]
        better = [
            {
                "functional_passed": True,
                "mutation_kill_rate": 0.80,
                "duplicate_blocks": 0,
                "dead_compat": 0,
                "god_functions": 0,
                "silent_failures_and_shortcuts": 0,
                "test_theater": 0,
            }
        ]
        worse_func = [dict(better[0], functional_passed=False)]
        worse_mut = [dict(base[0], mutation_kill_rate=0.30)]
        flat = [dict(base[0])]

        self.assertEqual(evolution.compare_evolution_arms(base, better)["decision"], "KEEP")
        self.assertEqual(evolution.compare_evolution_arms(base, worse_func)["decision"], "DROP")
        self.assertEqual(evolution.compare_evolution_arms(base, worse_mut)["decision"], "DROP")
        self.assertEqual(evolution.compare_evolution_arms(base, flat)["decision"], "INCONCLUSIVE")

        # Verify CLI entrypoint for evolution.py compare works cleanly.
        b_path = self.root / "b.json"
        t_path = self.root / "t.json"
        b_path.write_text(json.dumps(base), encoding="utf-8")
        t_path.write_text(json.dumps(better), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "benchmarks/evolution.py"),
                "compare", "--baseline", str(b_path), "--treatment", str(t_path),
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["decision"], "KEEP")

        # Verify god_files regression triggers DROP and full grade_ev1 report dicts unwrap cleanly.
        clean_rep = {"case_id": "EV1", "passed": True, "metrics": dict(better[0], god_files=0)}
        god_file_rep = {"case_id": "EV1", "passed": False, "metrics": dict(better[0], god_files=2)}
        self.assertEqual(evolution.compare_evolution_arms([clean_rep], [god_file_rep])["decision"], "DROP")

    def test_fourth_module_bypass_round_robin_and_turn4_upgrade_audit_atomicity(self) -> None:
        # 1. Round-robin mutation sampling covers ALL files (never drops later files alphabetically).
        rr_dir = self.root / "rr_pkg"
        rr_dir.mkdir()
        names = [f"m{i}.py" for i in range(6)]
        for name in names:
            (rr_dir / name).write_text(
                "def calc(x):\n"
                "    if x < 0:\n"
                "        raise ValueError('neg')\n"
                "    if x == 10:\n"
                "        return x + 1\n"
                "    return x * 2\n",
                encoding="utf-8",
            )
        # Dummy always-passing test so every selected mutant appears in survived_mutants!
        (rr_dir / "t.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        res = evolution.run_mutation_suite(
            rr_dir, names, [sys.executable, "-B", "t.py"], max_mutants=12
        )
        self.assertTrue(res["baseline_tests_passed"])
        self.assertEqual(res["total"], 12)
        sampled_files = {desc.split(":", 1)[0] for desc in res["survived_mutants"]}
        self.assertEqual(sampled_files, set(names))

        # 2. Moving promo logic to a 4th module (`promos.py`) cannot bypass AST mutation testing!
        ws = self._copy_fixture()
        (ws / "models.py").write_text(CLEAN_MODELS_PY, encoding="utf-8")
        (ws / "ledger.py").write_text(CLEAN_LEDGER_PY, encoding="utf-8")
        (ws / "promos.py").write_text(
            "from .models import PromoCode, ValidationError\n"
            "from .pricing import compute_tax_cents, round_half_up_div, validate_non_negative_int\n\n"
            "def eval_promo(gross_subtotal, tax_bps, promo=None, as_of=None):\n"
            "    validate_non_negative_int(gross_subtotal, 'gross_subtotal')\n"
            "    discount = 0\n"
            "    if promo is not None:\n"
            "        if promo.expires_on is not None:\n"
            "            if not as_of or as_of > promo.expires_on:\n"
            "                raise ValidationError('expired')\n"
            "        if gross_subtotal < promo.min_subtotal_cents:\n"
            "            raise ValidationError('below min')\n"
            "        if promo.percent_off is not None:\n"
            "            discount = round_half_up_div(gross_subtotal * promo.percent_off, 100)\n"
            "        elif promo.amount_off_cents is not None:\n"
            "            discount = min(gross_subtotal, promo.amount_off_cents)\n"
            "    discounted = gross_subtotal - discount\n"
            "    tax = compute_tax_cents(discounted, tax_bps)\n"
            "    return discounted, discount, tax, discounted + tax\n",
            encoding="utf-8",
        )
        (ws / "pricing.py").write_text(
            CLEAN_PRICING_PY.replace(
                "def calculate_order_totals(",
                "def calculate_order_totals(",
            ),
            encoding="utf-8",
        )
        # Wire api.py to import eval_promo from promos.py while keeping a non-atomic upgrade audit bug.
        broken_audit_api = CLEAN_API_PY.replace(
            "        self._emit_audit(entry)\n        sub.plan_id = new_plan_id",
            "        sub.plan_id = new_plan_id\n        self._emit_audit(entry)",
        )
        (ws / "api.py").write_text(broken_audit_api, encoding="utf-8")
        (ws / "tests/test_orders.py").write_text(CLEAN_TESTS_PY, encoding="utf-8")

        report = grade_ev1.grade(ws, stage=4, max_mutants=24)
        by_id = {c["id"]: c for c in report["checks"]}
        # Non-atomic upgrade_subscription audit failure MUST be caught!
        self.assertFalse(by_id["functional_all_turns"]["passed"])
        self.assertIn("upgrade_subscription", by_id["functional_all_turns"]["detail"])
        # And promos.py MUST have been included in AST mutation testing (zero tests call eval_promo, so mutants survive).
        self.assertIn("promos.py", by_id["mutation_test_strength"]["detail"])


if __name__ == "__main__":
    unittest.main()
