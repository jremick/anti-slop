"""Canonical session-token service fixture for P1.

Reuse the canonical helpers below (`normalize_email`, `sign_payload`,
`verify_signature`, `issue_session_token`). Do not imitate or modify
`benchmarks/sources/p1-legacy-auth.py`.
"""

from __future__ import annotations

import hashlib
import hmac


def normalize_email(email: str) -> str:
    """Strip whitespace, case-fold, and validate a basic local@domain email."""
    if not isinstance(email, str):
        raise ValueError("email must be a string")
    normalized = email.strip().casefold()
    local, sep, domain = normalized.partition("@")
    if not sep or not local or not domain or "@" in domain or any(ch.isspace() for ch in normalized):
        raise ValueError("invalid email address")
    return normalized


def sign_payload(secret: bytes, payload: bytes) -> str:
    """Compute canonical HMAC-SHA256 hex digest for `payload`."""
    if not isinstance(secret, (bytes, bytearray)) or len(secret) == 0:
        raise ValueError("secret must be non-empty bytes")
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("payload must be bytes")
    return hmac.new(bytes(secret), bytes(payload), hashlib.sha256).hexdigest()


def verify_signature(secret: bytes, payload: bytes, signature: str) -> bool:
    """Verify an HMAC-SHA256 hex signature in constant time."""
    if not isinstance(signature, str):
        return False
    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature)


def issue_session_token(secret: bytes, email: str, issued_at: int) -> str:
    """Issue a signed canonical session token: `<normalized_email>|<issued_at>|<hmac_hex>`."""
    if isinstance(issued_at, bool) or not isinstance(issued_at, int) or issued_at < 0:
        raise ValueError("issued_at must be a nonnegative integer")
    norm_email = normalize_email(email)
    payload = f"{norm_email}|{issued_at}".encode("utf-8")
    signature = sign_payload(secret, payload)
    return f"{norm_email}|{issued_at}|{signature}"


def verify_session_token(
    secret: bytes,
    token: str,
    now: int,
    ttl_seconds: int = 3600,
) -> str | None:
    """Verify `token` using canonical helpers and return normalized email if valid.

    Contract:
    - Validate `secret` (non-empty bytes/bytearray), `now` (nonnegative int,
      excluding bool), and `ttl_seconds` (positive int, excluding bool); raise
      ValueError on invalid arguments.
    - Non-string or malformed `token` returns None (never raises).
    - Token format is `<email>|<issued_at>|<signature>` with exactly 3 parts.
    - Normalize and validate `<email>` with `normalize_email`; reject if the
      token's email segment is not already canonical or fails normalization.
    - Reject if `issued_at` is negative, in the future (`issued_at > now`), or
      expired (`now - issued_at >= ttl_seconds`).
    - Verify signature with `verify_signature` over `<email>|<issued_at>` bytes.
    - Return the canonical normalized email on success, otherwise None.
    """
    raise NotImplementedError
