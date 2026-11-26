"""FROZEN EXTERNAL COMPATIBILITY SHIM — DO NOT MODIFY OR DELETE.

External downstream v1 jobs import `v1_legacy_fee` directly from this module.
"""

from .legacy_math import compute_float_fee


def v1_legacy_fee(amount_cents: int, bps: int) -> int:
    """Preserved v1 external API; intentionally wraps `legacy_math`."""
    return compute_float_fee(amount_cents, bps)
