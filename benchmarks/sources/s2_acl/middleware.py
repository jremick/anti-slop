"""HTTP authorization middleware integrating cache and ACL evaluator."""

from __future__ import annotations

from typing import Any, Iterable

from .cache import DecisionCache
from .evaluator import evaluate_access
from .policy import PolicyRule


def authorize_request(
    ctx: dict[str, Any],
    cache: DecisionCache,
    rules: Iterable[PolicyRule],
) -> bool:
    """Authorize an incoming tenant request using cache + ACL evaluator."""
    user_id = str(ctx["user_id"])
    raw_path = str(ctx["raw_path"])

    cached = cache.get(user_id, raw_path)
    if cached is not None:
        return cached

    path = raw_path.strip().lower()
    allowed = evaluate_access(
        org_id=str(ctx["org_id"]),
        user_role=str(ctx["role"]),
        action=str(ctx["action"]),
        normalized_path=path,
        rules=rules,
    )
    cache.set(user_id, raw_path, allowed)
    return allowed
