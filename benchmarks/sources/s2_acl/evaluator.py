"""Tenant-scoped ACL evaluator (deny-overrides-allow)."""

from __future__ import annotations

from typing import Iterable

from .policy import PolicyRule
from .roles import role_allows


def _prefix_matches(resource_path: str, prefix: str) -> bool:
    norm_prefix = prefix.rstrip("/") or "/"
    if norm_prefix == "/":
        return True
    return resource_path == norm_prefix or resource_path.startswith(norm_prefix + "/")


def evaluate_access(
    org_id: str,
    user_role: str,
    action: str,
    normalized_path: str,
    rules: Iterable[PolicyRule],
) -> bool:
    """Evaluate tenant ACL rules with strict deny-before-allow precedence."""
    tenant_rules = [
        rule for rule in rules
        if rule.org_id == org_id
        and (rule.role == "*" or rule.role == user_role)
        and _prefix_matches(normalized_path, rule.resource_prefix)
    ]
    # Explicit deny always wins over any allow rule.
    for rule in tenant_rules:
        if rule.effect == "deny":
            return False

    if not role_allows(user_role, action):
        return False

    return any(rule.effect == "allow" for rule in tenant_rules)
