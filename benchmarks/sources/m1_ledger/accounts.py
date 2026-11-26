"""Account validation utilities."""

from __future__ import annotations

from typing import Any


def normalize_account_id(account_id: Any) -> str:
    """Validate and strip an account identifier."""
    if not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("account_id must be a nonempty string")
    return account_id.strip()
