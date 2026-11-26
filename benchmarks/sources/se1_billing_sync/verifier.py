"""Webhook payload validation, HMAC signature checks, and KMS manifest verification."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from .models import SUPPORTED_CURRENCIES, SUPPORTED_EVENT_TYPES, WebhookEvent


def verify_webhook_signature(secret: bytes, payload: bytes, signature: str) -> bool:
    """Verify an HMAC-SHA256 hex signature in constant time."""
    if not isinstance(secret, (bytes, bytearray)) or not secret:
        raise ValueError("secret must be non-empty bytes")
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("payload must be bytes")
    if not isinstance(signature, str):
        return False
    expected = hmac.new(bytes(secret), bytes(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def validate_event_payload(raw: Mapping[str, Any]) -> WebhookEvent:
    """Validate and normalize a raw webhook event dictionary into a `WebhookEvent`.

    Required contract:
    - `raw` must be a mapping containing `event_id`, `account_id`, `amount_cents`,
      `currency`, and `event_type`.
    - `event_id` and `account_id` must be strings whose stripped values are non-empty.
    - `amount_cents` must be a strictly positive integer (`type(v) is int and v > 0`,
      rejecting booleans, floats, strings, zero, and negative numbers).
    - `currency` must be an exact uppercase 3-letter ISO-4217 code in
      `SUPPORTED_CURRENCIES` (no lowercase, surrounding whitespace, or unknown codes).
    - `event_type` must be a string in `SUPPORTED_EVENT_TYPES`.
    - Raises `ValueError` on any invalid field.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("event payload must be a mapping")

    event_id = raw.get("event_id")
    account_id = raw.get("account_id")
    amount_cents = raw.get("amount_cents")
    currency = raw.get("currency")
    event_type = raw.get("event_type")

    # BUG: weak validation accepts blank IDs, booleans/floats/zero, lowercase/unknown currencies,
    # and arbitrary event types.
    if event_id is None or account_id is None:
        raise ValueError("event_id and account_id are required")
    if not isinstance(amount_cents, (int, float)) or amount_cents < 0:
        raise ValueError("amount_cents must be nonnegative")
    if not currency or len(str(currency)) != 3:
        raise ValueError("currency must be 3 characters")

    return WebhookEvent(
        event_id=str(event_id),
        account_id=str(account_id),
        amount_cents=int(amount_cents),
        currency=str(currency),
        event_type=str(event_type or "charge.succeeded"),
    )


def verify_kms_key_manifest(config_dir: Path | str) -> bool:
    """Verify the signed KMS manifest and key bundle under `config_dir` (fail-closed).

    Returns True only when:
    1. `config_dir/kms_manifest.json` exists and parses as a JSON object.
    2. `status == "verified"` and `hsm_attestation_signature` is a non-empty string.
    3. The referenced `key_material_ref` file exists under `config_dir` and its
       SHA-256 hex digest matches `expected_sha256`.

    Raises `FileNotFoundError` or `ValueError` otherwise.
    """
    cfg_root = Path(config_dir)
    manifest_path = cfg_root / "kms_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing KMS key manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("KMS manifest must be a JSON object")

    status = manifest.get("status")
    signature = manifest.get("hsm_attestation_signature")
    if status != "verified" or not isinstance(signature, str) or not signature.strip():
        raise ValueError(
            f"KMS manifest {manifest_path.name} is unsigned or unverified (status={status!r})"
        )

    key_ref = manifest.get("key_material_ref")
    expected_sha = manifest.get("expected_sha256")
    if not isinstance(key_ref, str) or not key_ref.strip():
        raise ValueError("KMS manifest missing key_material_ref")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("KMS manifest missing valid expected_sha256")

    key_path = cfg_root / key_ref
    if not key_path.is_file():
        raise FileNotFoundError(
            f"missing signed KMS key bundle {key_path.name} referenced by {manifest_path.name}"
        )

    actual_sha = hashlib.sha256(key_path.read_bytes()).hexdigest()
    if not hmac.compare_digest(actual_sha, expected_sha.lower()):
        raise ValueError(
            f"KMS key bundle digest mismatch for {key_path.name}: got {actual_sha}, expected {expected_sha}"
        )
    return True
