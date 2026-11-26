"""FROZEN LEGACY MODULE — DO NOT MODIFY OR IMPORT FROM NEW CODE.

Retained solely for external v1 batch reconcilers (`compat_v1.py`).
Uses floating-point percentages and Python's round-half-to-even `round()`.
"""


def compute_float_fee(amount_cents: int, bps: int) -> int:
    """Legacy float-based fee calculation (suffers binary float rounding drift)."""
    dollars = amount_cents / 100.0
    fee_dollars = dollars * (bps / 10000.0)
    return int(round(fee_dollars * 100.0))
