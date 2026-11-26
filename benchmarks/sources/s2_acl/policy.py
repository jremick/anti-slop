"""Tenant policy model and canonical path normalization."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath


@dataclass(frozen=True)
class PolicyRule:
    org_id: str
    resource_prefix: str
    role: str  # exact role name or "*"
    effect: str  # "allow" or "deny"


def normalize_resource_path(raw_path: str) -> str:
    """Canonicalize a resource path, resolving `.` and `..` segments cleanly."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("resource path must be a nonempty string")
    cleaned = raw_path.strip().lower()
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    normalized = posixpath.normpath(cleaned)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized
