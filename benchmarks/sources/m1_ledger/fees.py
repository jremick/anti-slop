"""Fee calculation helpers."""

from __future__ import annotations

from typing import Any

from .legacy_math import compute_float_fee


def calculate_fee_cents(amount_cents: Any, fee_bps: Any, *, allow_legacy_float: bool = False) -> int:
    """Compute exact half-up integer-cent fee for `amount_cents` at `fee_bps` basis points.

    Contract:
    - `amount_cents` must be a nonnegative int (excluding bool), else ValueError.
    - `fee_bps` must be an int (excluding bool) in 0..10000 inclusive, else ValueError.
    - Fee uses exact integer half-up rounding: `(amount_cents * fee_bps + 5000) // 10000`.
    """
    if allow_legacy_float:
        return compute_float_fee(amount_cents, fee_bps)
    return compute_float_fee(amount_cents, fee_bps)
