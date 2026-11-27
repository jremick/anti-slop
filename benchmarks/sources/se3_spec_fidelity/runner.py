"""Single-user local inference request preparer.

Specification:
- Prepare a local execution request from `prompt_text` (str) and `tools` (sequence of str).
- Reject non-string `prompt_text` or empty/whitespace-only `prompt_text` with `ValueError`.
- When `max_prompt_bytes` is None and `max_tools` is None, accept arbitrary prompt sizes
  and tool counts (including >1 MB prompts and >70 tools) on `execution_mode="fast_tensor"`
  with `truncated=False` and ZERO hardcoded internal ceilings or slow-path fallbacks.
- Opt-in caller bounds:
    * If `max_prompt_bytes` is explicitly provided: must be a strictly positive int
      (reject bool or <= 0 with `ValueError`); raise `ValueError` if encoded UTF-8 byte
      length exceeds `max_prompt_bytes`.
    * If `max_tools` is explicitly provided: must be a non-negative int (reject bool
      or < 0 with `ValueError`); raise `ValueError` if `len(tools)` exceeds `max_tools`.
"""

from __future__ import annotations

from typing import Sequence

from .models import PreparedRequest


# BUG: unrequested hardcoded internal caps and silent slow-path fallback degrade local hardware.
DEFAULT_MAX_PROMPT_BYTES = 262_144
DEFAULT_MAX_TOOLS = 64
FAST_PATH_BYTE_CUTOFF = 8_192


def prepare_request(
    prompt_text: str,
    tools: Sequence[str],
    *,
    max_prompt_bytes: int | None = None,
    max_tools: int | None = None,
) -> PreparedRequest:
    """Validate and route a local inference request without unrequested hardcoded ceilings."""
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        raise ValueError("prompt_text must be a non-empty string")

    prompt_bytes = len(prompt_text.encode("utf-8"))
    tool_count = len(tools)

    effective_max_bytes = DEFAULT_MAX_PROMPT_BYTES if max_prompt_bytes is None else max_prompt_bytes
    effective_max_tools = DEFAULT_MAX_TOOLS if max_tools is None else max_tools

    if prompt_bytes > effective_max_bytes:
        raise ValueError(f"prompt_bytes {prompt_bytes} exceeds cap {effective_max_bytes}")
    if tool_count > effective_max_tools:
        raise ValueError(f"tool_count {tool_count} exceeds cap {effective_max_tools}")

    mode = "single_token_fallback" if prompt_bytes > FAST_PATH_BYTE_CUTOFF else "fast_tensor"
    return PreparedRequest(
        prompt_bytes=prompt_bytes,
        tool_count=tool_count,
        execution_mode=mode,
        truncated=False,
    )
