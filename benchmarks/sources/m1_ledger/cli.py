"""CLI settlement summary helpers."""

from __future__ import annotations

from .fees import calculate_fee_cents
from .settlement import settle_entries
from .reporting import summarize_currency_totals


def run_settlement_summary(entries: list[dict[str, object]], fee_bps: int = 0) -> dict[str, object]:
    """Run settlement and reporting summary for CLI callers."""
    settled = settle_entries(entries, fee_bps=fee_bps)
    totals = summarize_currency_totals(settled)
    sample_fee = calculate_fee_cents(10000, fee_bps, allow_legacy_float=False)
    return {
        "settled": settled,
        "totals_by_currency": totals,
        "sample_fee_on_10000": sample_fee,
    }
