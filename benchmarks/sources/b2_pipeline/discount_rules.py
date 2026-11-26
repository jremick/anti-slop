"""Coupon discount rules (contains seeded non-stackable & cap bug)."""

from __future__ import annotations

from typing import Any


def apply_coupons(subtotal_cents: Any, coupons: list[dict[str, Any]]) -> int:
    """Apply promotional coupons to `subtotal_cents`.

    Contract:
    - `subtotal_cents` must be a nonnegative int (excluding bool), else ValueError.
    - Each coupon is a dict with `code` (str), `percent_off` (int in 0..100, excluding bool),
      and `stackable` (bool). Invalid entries raise ValueError.
    - Stackable coupons (`stackable=True`) sum together, capped at 50% maximum total discount.
    - Non-stackable coupons (`stackable=False`) CANNOT combine with any other coupon.
    - When both stackable and non-stackable coupons are present, select the single highest
      valid discount percentage between:
      (a) the largest single non-stackable coupon's `percent_off`, or
      (b) the capped sum (<= 50) of all `stackable=True` coupons.
    - Exact integer half-up discount: `subtotal_cents - (subtotal_cents * effective_pct + 50) // 100`.
    """
    if isinstance(subtotal_cents, bool) or not isinstance(subtotal_cents, int) or subtotal_cents < 0:
        raise ValueError("subtotal_cents must be a nonnegative int")
    if not isinstance(coupons, list):
        raise ValueError("coupons must be a list")

    # BUG: sums all coupons regardless of `stackable` and omits the 50% stackable cap.
    total_pct = 0
    for c in coupons:
        if not isinstance(c, dict):
            raise ValueError("coupon must be a dict")
        pct = c.get("percent_off")
        if isinstance(pct, bool) or not isinstance(pct, int) or pct < 0 or pct > 100:
            raise ValueError("percent_off must be an int in 0..100")
        total_pct += pct

    discount = (subtotal_cents * total_pct + 50) // 100
    return max(0, subtotal_cents - discount)
