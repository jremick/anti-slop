"""Role-to-action permission matrix (canonical, immutable)."""

from __future__ import annotations

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"read"}),
    "editor": frozenset({"read", "write"}),
    "admin": frozenset({"read", "write", "delete"}),
}


def role_allows(role: str, action: str) -> bool:
    """Return True strictly when `action` is an exact member of `role`'s permission set."""
    allowed_actions = ROLE_PERMISSIONS.get(role)
    if allowed_actions is None:
        return False
    return action in allowed_actions
