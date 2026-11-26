"""Canonical integer-cent pricing calculations for EV1 order ledger."""

from __future__ import annotations

from typing import Sequence, Tuple

from .models import LineItem, ValidationError


LEGACY_FLAT_FEE_CENTS = 500


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


def calculate_order_totals(
    items: Sequence[LineItem],
    *,
    tax_bps: int = 0,
    legacy_flat_fee: bool = False,
) -> Tuple[int, int, int]:
    """Return (subtotal_cents, tax_cents, total_cents) using exact integer cents."""
    subtotal = compute_subtotal_cents(items)
    if legacy_flat_fee:
        subtotal += LEGACY_FLAT_FEE_CENTS
    tax = compute_tax_cents(subtotal, tax_bps)
    return subtotal, tax, subtotal + tax
