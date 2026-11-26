"""Canonical integer-cent money primitives and exact allocation helpers.

All modules in `m1_ledger` should reuse these helpers rather than duplicating
currency validation or falling back to IEEE-754 floating-point math.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_CURRENCIES = frozenset({"USD", "EUR", "GBP", "AUD"})


def require_int_cents(value: Any, field: str = "cents", *, allow_negative: bool = False) -> int:
    """Validate an exact integer cent value (rejecting bool and non-int types)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int, got {type(value).__name__}")
    if not allow_negative and value < 0:
        raise ValueError(f"{field} must be nonnegative, got {value}")
    return int(value)


def validate_currency(code: Any) -> str:
    """Normalize and validate an ISO currency code against SUPPORTED_CURRENCIES."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("currency must be a nonempty string")
    normalized = code.strip().upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(f"unsupported currency: {code!r}")
    return normalized


def parse_cents(amount: Any) -> int:
    """Parse an exact integer cent amount (nonnegative int excluding bool)."""
    return require_int_cents(amount, "amount", allow_negative=False)


def allocate_proportional(total_cents: int, weights: list[int]) -> list[int]:
    """Split `total_cents` across positive integer weights with exact penny conservation.

    Uses largest-remainder allocation (tie-broken by earliest index) so that
    `sum(result) == total_cents` always holds without losing or creating cents.
    """
    total = require_int_cents(total_cents, "total_cents", allow_negative=False)
    if not isinstance(weights, list) or not weights:
        raise ValueError("weights must be a nonempty list of positive integers")
    clean_weights: list[int] = []
    for idx, w in enumerate(weights):
        val = require_int_cents(w, f"weights[{idx}]", allow_negative=False)
        if val <= 0:
            raise ValueError(f"weights[{idx}] must be positive")
        clean_weights.append(val)

    weight_sum = sum(clean_weights)
    shares: list[int] = []
    remainders: list[tuple[int, int]] = []
    for idx, w in enumerate(clean_weights):
        numerator = total * w
        base = numerator // weight_sum
        rem = numerator % weight_sum
        shares.append(base)
        remainders.append((rem, -idx))

    leftover = total - sum(shares)
    if leftover > 0:
        ranked = sorted(range(len(weights)), key=lambda i: remainders[i], reverse=True)
        for i in ranked[:leftover]:
            shares[i] += 1
    return shares


@dataclass(frozen=True)
class Money:
    cents: int
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cents", require_int_cents(self.cents, "cents", allow_negative=True))
        object.__setattr__(self, "currency", validate_currency(self.currency))
