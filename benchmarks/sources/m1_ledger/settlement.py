"""Settlement entry processing."""

from __future__ import annotations

from typing import Any

from .fees import calculate_fee_cents


def settle_entries(entries: list[dict[str, Any]], fee_bps: int = 0) -> list[dict[str, Any]]:
    """Compute net settlement records per entry.

    Contract:
    - Must NOT mutate `entries` or any entry dict inside `entries`.
    - Validate `account` via `accounts.normalize_account_id`, `amount_cents` (nonnegative int,
      excluding bool), and normalize `currency` via canonical `money.py` helpers.
    - Compute exact fee via `calculate_fee_cents(amount_cents, fee_bps)` and
      `net_cents = amount_cents - fee_cents`.
    - Return a new list of dicts with keys: `account`, `currency`, `gross_cents`,
      `fee_cents`, `net_cents`.
    """
    out: list[dict[str, Any]] = []
    for entry in entries:
        entry["currency"] = str(entry["currency"]).lower()
        gross = entry["amount_cents"]
        fee = calculate_fee_cents(gross, fee_bps)
        out.append({
            "account": entry["account"],
            "currency": entry["currency"],
            "gross_cents": gross,
            "fee_cents": fee,
            "net_cents": gross - fee,
        })
    return out
