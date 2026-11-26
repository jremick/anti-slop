"""Legacy auth helper retained for migration reference only; do not modify."""

from __future__ import annotations

import hashlib


def legacy_make_token(secret: str, email: str, issued_at: int) -> str:
    norm = email.lower()
    raw = f"{secret}:{norm}:{issued_at}".encode("utf-8")
    sig = hashlib.md5(raw).hexdigest()
    return f"{norm}|{issued_at}|{sig}"


def legacy_check_token(secret: str, token: str, now: int, ttl_seconds: int = 3600) -> str | None:
    try:
        email, ts_text, sig = token.split("|")
        issued_at = int(ts_text)
        expected = hashlib.md5(f"{secret}:{email.lower()}:{issued_at}".encode("utf-8")).hexdigest()
        if sig == expected and now - issued_at < ttl_seconds:
            return email.lower()
        return None
    except Exception:
        return None
