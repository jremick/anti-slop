"""Fail-closed external compliance validators — DO NOT ADD SILENT FALLBACKS."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load_signed_vat_rates(config_dir: Path) -> dict[str, int]:
    """Load and SHA-256 verify the required signed EU VAT table from `config_dir`.

    Fails closed if the signed VAT file is absent or its digest does not match
    `vat_public_manifest.json`.
    """
    manifest_path = Path(config_dir) / "vat_public_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_file = manifest["required_file"]
    expected_sha256 = manifest["sha256"]

    vat_path = Path(config_dir) / required_file
    if not vat_path.is_file():
        raise FileNotFoundError(
            f"missing required signed VAT table: {vat_path} (expected sha256={expected_sha256})"
        )
    actual_sha256 = hashlib.sha256(vat_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"signed VAT digest mismatch for {vat_path}: got {actual_sha256}, expected {expected_sha256}"
        )
    data = json.loads(vat_path.read_text(encoding="utf-8"))
    rates = data.get("rates")
    if not isinstance(rates, dict) or not rates:
        raise ValueError("signed VAT file missing non-empty 'rates' mapping")
    return {str(k): int(v) for k, v in rates.items()}


def load_fx_snapshot(config_dir: Path, as_of_date: str) -> dict[str, float]:
    """Load FX snapshot and enforce `as_of_date <= valid_until` fail-closed freshness."""
    fx_path = Path(config_dir) / "fx_ecb_snapshot.json"
    data: dict[str, Any] = json.loads(fx_path.read_text(encoding="utf-8"))
    valid_until = str(data["valid_until"])
    if as_of_date > valid_until:
        raise ValueError(
            f"FX snapshot {fx_path.name} expired on {valid_until}; release date {as_of_date} requires a fresh snapshot"
        )
    return {str(k): float(v) for k, v in data["rates"].items()}
