"""Double-entry posting helpers using canonical money primitives."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .accounts import normalize_account_id
from .money import require_int_cents, validate_currency


def post_entries(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize ledger posting entries without mutating inputs."""
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("each entry must be a mapping")
        if "account" not in entry or "amount_cents" not in entry or "currency" not in entry:
            raise ValueError("entry must include account, amount_cents, and currency")
        normalized.append({
            "account": normalize_account_id(entry["account"]),
            "amount_cents": require_int_cents(entry["amount_cents"], "amount_cents", allow_negative=True),
            "currency": validate_currency(entry["currency"]),
        })
    return normalized
