"""Core domain models for the EV1 order ledger fixture."""

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
