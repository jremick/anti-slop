"""Audit fee quote helpers."""

from __future__ import annotations

from .fees import calculate_fee_cents
from .money import validate_currency


def audit_fee_quote(amount_cents: int, fee_bps: int, currency: str) -> dict[str, object]:
    """Return an audited fee quote dict."""
    norm_currency = validate_currency(currency)
    fee = calculate_fee_cents(amount_cents, fee_bps, allow_legacy_float=False)
    return {
        "currency": norm_currency,
        "gross_cents": amount_cents,
        "fee_cents": fee,
        "net_cents": amount_cents - fee,
    }
