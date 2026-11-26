"""Volume tier pricing module (contains seeded boundary off-by-one bug)."""

from __future__ import annotations

from typing import Any


def calculate_tier_price(units: Any, unit_cents: Any) -> int:
    """Compute total integer-cent price with volume tier discounts.

    Contract:
    - `units` must be a positive int (>= 1, excluding bool), else ValueError.
    - `unit_cents` must be a nonnegative int (>= 0, excluding bool), else ValueError.
    - Tiers:
      * 1..9 units: 0% discount (0 bps)
      * 10..49 units: 10% discount (1000 bps)
      * 50+ units: 20% discount (2000 bps)
    - Exact integer half-up discount: `subtotal - (subtotal * discount_bps + 5000) // 10000`.
    """
    if isinstance(units, bool) or not isinstance(units, int) or units < 1:
        raise ValueError("units must be a positive int")
    if isinstance(unit_cents, bool) or not isinstance(unit_cents, int) or unit_cents < 0:
        raise ValueError("unit_cents must be a nonnegative int")

    subtotal = units * unit_cents
    # BUG: strict `>` instead of `>=` misprices exact tier boundaries 10 and 50.
    if units > 50:
        discount_bps = 2000
    elif units > 10:
        discount_bps = 1000
    else:
        discount_bps = 0

    discount = (subtotal * discount_bps + 5000) // 10000
    return subtotal - discount
