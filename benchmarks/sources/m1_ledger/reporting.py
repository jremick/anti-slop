"""Ledger reporting aggregations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .money import require_int_cents, validate_currency


def summarize_currency_totals(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Sum `net_cents` by normalized currency code.

    Contract:
    - Must validate each record has a valid `currency` and signed integer `net_cents`
      (excluding bool), raising ValueError on malformed or invalid records.
    - Must NOT swallow validation/key errors or mutate input records.
    """
    totals: dict[str, int] = {}
    for rec in records:
        try:
            curr = validate_currency(rec["currency"])
            amt = require_int_cents(rec["net_cents"], "net_cents", allow_negative=True)
            totals[curr] = totals.get(curr, 0) + amt
        except Exception:
            continue
    return totals
