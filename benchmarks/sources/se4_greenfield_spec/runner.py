"""Local workstation inference request preparer. See SPEC.md for full requirements."""

from __future__ import annotations

from typing import Sequence

from .models import PreparedBatch


def prepare_inference_batch(
    prompt_text: str,
    tools: Sequence[str],
    *,
    max_prompt_bytes: int | None = None,
    max_tools: int | None = None,
    force_mode: str | None = None,
) -> PreparedBatch:
    """Validate and prepare a local inference batch per SPEC.md."""
    raise NotImplementedError("Implement prepare_inference_batch per SPEC.md")
