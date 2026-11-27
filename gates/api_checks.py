#!/usr/bin/env python3
"""Deterministic Layer-1 validator for 2026 model API and harness configs.

Validates request, response, telemetry, and session configuration dicts for:
  - gpt-6.2-astra
  - gpt-6.2-sol
  - claude-opus-5-5
  - claude-fable-5-2
  - gemini-4-neon

Stdlib Python only (zero external dependencies). Returns structured
{"ok": bool, "model": str | None, "errors": [...], "warnings": [...]}.
CLI exits 0 when len(errors) == 0, and 1 when any error is present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SUPPORTED_MODELS: Tuple[str, ...] = (
    "gpt-6.2-astra",
    "gpt-6.2-sol",
    "claude-opus-5-5",
    "claude-fable-5-2",
    "gemini-4-neon",
)

GPT_VALID_EFFORTS = frozenset({"minimal", "low", "light", "medium", "high", "xhigh", "max"})
CLAUDE_VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
NEON_VALID_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "XHIGH"})

# [Heuristic] Starting thresholds documented in docs/operations-and-routing.md and docs/models.md;
# calibrate locally against telemetry rather than treating as universal constants.
DEFAULT_MAX_PR_COMMENTS = 10
DEFAULT_FABLE_MAX_SUBAGENTS = 3
DEFAULT_NEON_MAX_THOUGHT_RATIO = 4.0
DEFAULT_NEON_MAX_TTFT_SECONDS = 45.0

GPT_BANNED_CONCISE_RE = re.compile(
    r"\b(?:be\s+concise|keep\s+it\s+short|keep\s+(?:your\s+)?(?:answers?|responses?|output)\s+short)\b",
    re.IGNORECASE,
)

CLAUDE_ABSOLUTE_RE = re.compile(r"\b(ALWAYS|NEVER)\b")
CLAUDE_EXCEPTION_RE = re.compile(
    r"\b(?:unless|except|when|if|excluding|other\s+than|save\s+for|with\s+the\s+exception|outside\s+of)\b",
    re.IGNORECASE,
)

FABLE_DOWNGRADE_RE = re.compile(
    r"^claude-opus-(?:4[-.]8(?:[-.]\S*)?|5(?:-(?:20\d{6}|preview\S*))?)$",
    re.IGNORECASE,
)

PR_REVIEW_MODES = frozenset({
    "pr_review",
    "pr-review",
    "code_review",
    "code-review",
    "review",
})

STRUCTURED_OR_REVIEW_MODES = frozenset({
    "structured",
    "structured_output",
    "structured-output",
    "review",
    "pr_review",
    "pr-review",
    "code_review",
    "code-review",
    "security_review",
    "security-review",
    "audit",
})

LOOP_MODES = frozenset({
    "agent_loop",
    "agent-loop",
    "multi_turn",
    "multi-turn",
    "multi_step",
    "multi-step",
    "loop",
})

ML_RD_WORKLOADS = frozenset({
    "ml_research",
    "ml-research",
    "kernel_opt",
    "kernel-opt",
    "local_inference",
    "local-inference",
    "pretraining",
    "ai_rd",
    "ai-rd",
})

_PROVIDER_FAMILY_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("anthropic", re.compile(r"\b(?:claude|anthropic|opus|sonnet|haiku|fable|mythos)\b", re.IGNORECASE)),
    ("openai", re.compile(r"\b(?:gpt-[0-9]|openai|codex|chatgpt|o[134]-mini|o[134]-pro|astra|sol)\b", re.IGNORECASE)),
    ("google", re.compile(r"\b(?:gemini|google|antigravity|deepmind|neon|argon|carbon|hydrogen)\b", re.IGNORECASE)),
)


def _infer_provider_family(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    cleaned = raw.strip().lower()
    if cleaned in ("anthropic", "openai", "google"):
        return cleaned
    for provider, pat in _PROVIDER_FAMILY_PATTERNS:
        if pat.search(cleaned):
            return provider
    return None


def _finding(code: str, severity: str, message: str, remediation: str) -> Dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "remediation": remediation,
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_model(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def _canonical_family(model: str) -> Optional[str]:
    """Map an exact model ID or dated snapshot to one of the 5 target models."""
    for target in SUPPORTED_MODELS:
        if model == target or model.startswith(target + "-") or model.startswith(target + "@"):
            return target
    return None


def _subdict(mapping: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    for key in keys:
        val = mapping.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _lookup(dicts: Sequence[Dict[str, Any]], *keys: str) -> Tuple[bool, Any]:
    """Return (found, value) for the first matching key across candidate dicts."""
    for d in dicts:
        if not isinstance(d, dict):
            continue
        for key in keys:
            if key in d and d[key] is not None:
                return True, d[key]
    return False, None


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        if isinstance(text, str):
            return text
    return ""


def _collect_gpt_system_prompts(req: Dict[str, Any], root: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Collect (source_label, text) pairs from GPT-6.2 system/developer prompt fields."""
    prompts: List[Tuple[str, str]] = []
    seen_ids: set = set()
    for container_name, container in (("request", req), ("config", root)):
        if id(container) in seen_ids or not isinstance(container, dict):
            continue
        seen_ids.add(id(container))
        for key in ("instructions", "system", "system_prompt", "developer_prompt"):
            if key in container and container[key]:
                text = _extract_text(container[key])
                if text:
                    prompts.append((key, text))
        for list_key in ("input", "messages"):
            items = container.get(list_key)
            if isinstance(items, list):
                for idx, item in enumerate(items):
                    if isinstance(item, dict):
                        role = str(item.get("role", "")).strip().lower()
                        if role in ("developer", "system"):
                            text = _extract_text(item.get("content"))
                            if text:
                                prompts.append((f"{list_key}[{idx}]({role})", text))
    return prompts


def _is_multi_turn_loop(req: Dict[str, Any], sess: Dict[str, Any], harness: Dict[str, Any], root: Dict[str, Any]) -> bool:
    dicts = (sess, harness, req, root)
    for flag in ("multi_turn", "is_multi_turn", "multi_turn_loop", "multi_step", "is_multi_step", "loop", "in_loop"):
        found, val = _lookup(dicts, flag)
        if found:
            return bool(val)
    found, mode = _lookup(dicts, "mode", "task_type", "workload")
    if found and isinstance(mode, str) and mode.strip().lower() in LOOP_MODES:
        return True
    for num_key in ("max_turns", "turn_count", "turns_count", "steps", "max_steps"):
        found, val = _lookup(dicts, num_key)
        if found and _is_number(val) and val > 1:
            return True
    for list_key in ("messages", "contents", "turns"):
        found, items = _lookup((req, sess, root), list_key)
        if found and isinstance(items, list):
            assistant_turns = 0
            for item in items:
                if isinstance(item, dict):
                    role = str(item.get("role", "")).strip().lower()
                    if role in ("assistant", "model"):
                        assistant_turns += 1
            if assistant_turns >= 1:
                return True
    return False


def validate_claude_md(text: str) -> List[Dict[str, str]]:
    """Warn on unqualified uppercase ALWAYS/NEVER directives in CLAUDE.md text.

    Lines inside fenced code blocks are ignored. Directives that contain an
    explicit exception clause (e.g., 'unless', 'except', 'when', 'if') pass.
    """
    warnings: List[Dict[str, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len and stripped[len(marker):].strip() == "":
                in_fence = False
            continue
        if in_fence:
            continue

        match = CLAUDE_ABSOLUTE_RE.search(line)
        if match and not CLAUDE_EXCEPTION_RE.search(line):
            warnings.append(
                _finding(
                    code="CLAUDE-MD-UNQUALIFIED-ABSOLUTE",
                    severity="warning",
                    message=(
                        f"CLAUDE.md line {lineno} uses unqualified '{match.group(1)}' "
                        "without an exception clause."
                    ),
                    remediation=(
                        "Add an explicit exception clause (e.g., 'unless ...' or 'except when ...') "
                        "to prevent literal rule deadlocks and over-cautious refusals."
                    ),
                )
            )
    return warnings


def _validate_gpt62(
    family: str,
    config: Dict[str, Any],
    req: Dict[str, Any],
    sess: Dict[str, Any],
    harness: Dict[str, Any],
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
) -> None:
    reasoning = _subdict(req, "reasoning") or _subdict(config, "reasoning")
    found_effort, effort_raw = _lookup((reasoning, req, config), "effort", "reasoning_effort")
    effort: Optional[str] = None
    if found_effort:
        effort = str(effort_raw).strip().lower()
        if effort == "none":
            errors.append(
                _finding(
                    code="GPT-EFFORT-NONE",
                    severity="error",
                    message=f"{family} rejects reasoning.effort='none' with HTTP 400.",
                    remediation="Set reasoning.effort to one of: minimal, low/light, medium, high, xhigh, max (default: medium).",
                )
            )
        elif effort not in GPT_VALID_EFFORTS:
            errors.append(
                _finding(
                    code="GPT-EFFORT-INVALID",
                    severity="error",
                    message=f"{family} received unsupported reasoning.effort='{effort_raw}'.",
                    remediation="Use one of: minimal, low/light, medium, high, xhigh, max.",
                )
            )

    found_tier, tier_raw = _lookup((req, config), "service_tier")
    if found_tier and str(tier_raw).strip().lower() == "flex":
        errors.append(
            _finding(
                code="GPT-FLEX-TIER",
                severity="error",
                message=f"{family} does not support service_tier='flex'.",
                remediation="Remove service_tier='flex' or use standard / background mode.",
            )
        )

    found_instr, instructions = _lookup((req, config), "instructions")
    if found_instr and isinstance(instructions, str) and instructions.strip():
        errors.append(
            _finding(
                code="GPT-INSTRUCTIONS-CACHE",
                severity="error",
                message=(
                    f"{family} config places prompt text in top-level 'instructions', "
                    "which breaks static prefix prompt caching."
                ),
                remediation=(
                    "Move static prompt rules into an immutable input[0] message with "
                    "role='developer' and omit top-level 'instructions'."
                ),
            )
        )

    for source_label, prompt_text in _collect_gpt_system_prompts(req, config):
        match = GPT_BANNED_CONCISE_RE.search(prompt_text)
        if match:
            errors.append(
                _finding(
                    code="GPT-BANNED-CONCISE-PROMPT",
                    severity="error",
                    message=(
                        f"{family} prompt ({source_label}) contains banned legacy phrase "
                        f"'{match.group(0)}', which amplifies confident-concise omission."
                    ),
                    remediation=(
                        "Remove 'be concise' / 'keep it short' from GPT-6.2 developer/system prompts; "
                        "specify concrete output structure and required caveats instead."
                    ),
                )
            )

    # Check mid-thread Astra <-> Sol swap.
    observed_families: set = {family}
    for key in ("previous_model", "prior_model", "initial_model"):
        found_prev, prev_val = _lookup((sess, harness, req, config), key)
        if found_prev:
            prev_norm = _normalize_model(prev_val)
            if prev_norm:
                prev_fam = _canonical_family(prev_norm)
                if prev_fam in ("gpt-6.2-astra", "gpt-6.2-sol"):
                    observed_families.add(prev_fam)
    for hist_key in ("thread_models", "session_models", "model_history"):
        found_hist, hist = _lookup((sess, harness, req, config), hist_key)
        if found_hist and isinstance(hist, list):
            for entry in hist:
                entry_norm = _normalize_model(entry)
                if entry_norm:
                    entry_fam = _canonical_family(entry_norm)
                    if entry_fam in ("gpt-6.2-astra", "gpt-6.2-sol"):
                        observed_families.add(entry_fam)
    found_turns, turns = _lookup((sess, req, config), "turns", "history")
    if found_turns and isinstance(turns, list):
        for turn in turns:
            if isinstance(turn, dict):
                t_norm = _normalize_model(turn.get("model"))
                if t_norm:
                    t_fam = _canonical_family(t_norm)
                    if t_fam in ("gpt-6.2-astra", "gpt-6.2-sol"):
                        observed_families.add(t_fam)

    if "gpt-6.2-astra" in observed_families and "gpt-6.2-sol" in observed_families:
        errors.append(
            _finding(
                code="GPT-MID-THREAD-SWAP",
                severity="error",
                message=(
                    "Mid-thread swap detected between gpt-6.2-astra and gpt-6.2-sol, "
                    "which invalidates reasoning state and prefix caches."
                ),
                remediation=(
                    "Keep one GPT-6.2 variant per thread; start a fresh context handoff "
                    "when switching between Astra and Sol."
                ),
            )
        )

    # Sol PR review effort & PR comment cap warnings.
    found_task, task_raw = _lookup((harness, sess, req, config), "task_type", "workload", "task", "mode")
    found_pr_flag, pr_flag = _lookup((harness, sess, req, config), "is_pr_review")
    is_pr_review = bool(pr_flag) if found_pr_flag else False
    if found_task and isinstance(task_raw, str) and task_raw.strip().lower() in PR_REVIEW_MODES:
        is_pr_review = True

    if family == "gpt-6.2-sol" and is_pr_review and effort in ("high", "xhigh", "max"):
        warnings.append(
            _finding(
                code="GPT-SOL-PR-HIGH-EFFORT",
                severity="warning",
                message=(
                    f"gpt-6.2-sol PR review at reasoning.effort='{effort}' triggers a ~3x "
                    "nitpick surge and lower review precision."
                ),
                remediation="Set reasoning.effort to 'low' or 'medium' for gpt-6.2-sol PR reviews.",
            )
        )

    found_cap, cap_raw = _lookup(
        (harness, sess, req, config),
        "pr_comment_cap",
        "max_review_comments",
        "review_comment_cap",
        "comment_cap",
    )
    if found_cap and _is_number(cap_raw) and cap_raw > DEFAULT_MAX_PR_COMMENTS:
        warnings.append(
            _finding(
                code="GPT-PR-COMMENT-CAP",
                severity="warning",
                message=(
                    f"PR review comment cap ({cap_raw}) exceeds the recommended "
                    f"starting limit of {DEFAULT_MAX_PR_COMMENTS} [Heuristic]."
                ),
                remediation=(
                    f"Cap automated PR review comments at <= {DEFAULT_MAX_PR_COMMENTS} [Heuristic] "
                    "and drop low-signal nitpicks."
                ),
            )
        )


def _check_claude_thinking_mutations(
    req: Dict[str, Any],
    sess: Dict[str, Any],
    harness: Dict[str, Any],
    config: Dict[str, Any],
) -> Optional[str]:
    dicts = (sess, harness, req, config)
    found_ao, append_only = _lookup(dicts, "thinking_blocks_append_only")
    if found_ao and append_only is False:
        return "thinking_blocks_append_only is false"

    for bad_flag in ("thinking_block_mutated", "mutate_thinking_blocks", "strip_thinking_blocks", "prefix_edited"):
        found, val = _lookup(dicts, bad_flag)
        if found and val is True:
            return f"{bad_flag} is true"

    found_prev, prev_blocks = _lookup(dicts, "previous_thinking_blocks")
    found_curr, curr_blocks = _lookup(dicts, "current_thinking_blocks", "thinking_blocks")
    if found_prev and found_curr and isinstance(prev_blocks, list) and isinstance(curr_blocks, list):
        if len(curr_blocks) < len(prev_blocks) or curr_blocks[: len(prev_blocks)] != prev_blocks:
            return "prior thinking blocks were modified or truncated instead of appended"

    found_msgs, messages = _lookup((req, sess, config), "messages")
    if found_msgs and isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        if block.get("edited") is True or block.get("mutated") is True:
                            return "assistant message contains an edited/mutated thinking block"
    return None


DEFAULT_CLAUDE_LONG_HORIZON_TURNS = 10


def _is_enabled_feature(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if _is_number(val):
        return val > 0
    if isinstance(val, str):
        return val.strip().lower() not in ("", "false", "0", "none", "off", "disabled")
    if isinstance(val, list):
        return len(val) > 0
    if isinstance(val, dict):
        if val.get("enabled") is False:
            return False
        if "edits" in val:
            edits = val["edits"]
            return isinstance(edits, list) and len(edits) > 0
        return any(v not in (False, None, "", [], {}) for v in val.values())
    return False


def _has_observation_masking(dicts: Sequence[Dict[str, Any]]) -> bool:
    for key in ("observation_masking", "mask_observations", "tool_result_masking"):
        found, val = _lookup(dicts, key)
        if found and _is_enabled_feature(val):
            return True
    found_strat, strat = _lookup(dicts, "compaction_strategy")
    if found_strat and isinstance(strat, str):
        norm = strat.strip().lower().replace("-", "_")
        if "mask" in norm or "hybrid" in norm:
            return True
    return False


def _has_checkpoint_reset(dicts: Sequence[Dict[str, Any]]) -> bool:
    for key in ("checkpoint_reset", "reset_checkpoints", "fresh_checkpoint_reset", "reset_boundary"):
        found, val = _lookup(dicts, key)
        if found and _is_enabled_feature(val):
            return True
    return False


def _has_claude_tool_clearing(dicts: Sequence[Dict[str, Any]]) -> bool:
    if _has_observation_masking(dicts):
        return True
    for key in ("context_management", "clear_tool_uses", "clear_tool_uses_20250919"):
        found, val = _lookup(dicts, key)
        if found and _is_enabled_feature(val):
            return True
    return False


def _validate_claude(
    family: str,
    config: Dict[str, Any],
    req: Dict[str, Any],
    resp: Dict[str, Any],
    sess: Dict[str, Any],
    harness: Dict[str, Any],
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
) -> None:
    thinking_raw = req.get("thinking") if "thinking" in req else config.get("thinking")
    thinking = thinking_raw if isinstance(thinking_raw, dict) else {}

    if thinking_raw is False or (
        isinstance(thinking, dict)
        and str(thinking.get("type", "")).strip().lower() == "disabled"
    ):
        errors.append(
            _finding(
                code="CLAUDE-THINKING-DISABLED",
                severity="error",
                message=f"{family} requires adaptive thinking always on; thinking.type='disabled' returns HTTP 400.",
                remediation="Enable adaptive thinking (thinking.type='adaptive') and tune effort via output_config.effort.",
            )
        )

    found_budget, _ = _lookup((thinking, req, config), "budget_tokens")
    if found_budget:
        errors.append(
            _finding(
                code="CLAUDE-LEGACY-BUDGET-TOKENS",
                severity="error",
                message=f"{family} rejects legacy 'budget_tokens' with HTTP 400.",
                remediation="Remove 'budget_tokens' and control reasoning depth with output_config.effort.",
            )
        )

    mutation_reason = _check_claude_thinking_mutations(req, sess, harness, config)
    if mutation_reason:
        errors.append(
            _finding(
                code="CLAUDE-THINKING-MUTATION",
                severity="error",
                message=(
                    f"{family} detected non-append-only thinking block mutation ({mutation_reason}); "
                    "prefix edits return HTTP 400 and break thinking-block binding."
                ),
                remediation="Preserve all prior assistant thinking blocks verbatim and append-only.",
            )
        )

    # Check CLAUDE.md unqualified ALWAYS/NEVER warnings.
    found_cmd, claude_md_text = _lookup((harness, sess, req, config), "claude_md", "claude_md_content", "claude_md_text")
    if found_cmd and isinstance(claude_md_text, str):
        warnings.extend(validate_claude_md(claude_md_text))
    else:
        found_path, claude_md_path = _lookup((harness, sess, req, config), "claude_md_path")
        if found_path and isinstance(claude_md_path, str):
            p = Path(claude_md_path)
            if p.is_file():
                warnings.extend(validate_claude_md(p.read_text(encoding="utf-8")))

    # Context-hygiene warning: long-horizon Claude sessions without tool-result clearing / observation masking.
    ctx_dicts = (harness, sess, req, config)
    found_lh, lh_val = _lookup(ctx_dicts, "long_horizon")
    found_mt, mt_val = _lookup(ctx_dicts, "max_turns")
    is_long_horizon = bool(lh_val) if found_lh else False
    if found_mt and _is_number(mt_val) and mt_val >= DEFAULT_CLAUDE_LONG_HORIZON_TURNS:
        is_long_horizon = True
    if is_long_horizon and not _has_claude_tool_clearing(ctx_dicts):
        trigger = (
            f"max_turns={mt_val}"
            if (found_mt and _is_number(mt_val) and mt_val >= DEFAULT_CLAUDE_LONG_HORIZON_TURNS)
            else "long_horizon=true"
        )
        warnings.append(
            _finding(
                code="CLAUDE-MISSING-TOOL-CLEAR",
                severity="warning",
                message=(
                    f"{family} declares a long-horizon session ({trigger}) without "
                    "context_management / clear_tool_uses or observation masking configured "
                    "(Anthropic tool-result clearing: +29% alone / +39% with Memory Tool eval lift; "
                    "JetBrains observation masking: ~52% cost reduction, arXiv:2508.21433)."
                ),
                remediation=(
                    "Enable server-side context_management (e.g., edits=[{'type': 'clear_tool_uses_20250919'}]), "
                    "clear_tool_uses, or observation_masking on long-horizon Claude harnesses."
                ),
            )
        )

    # Fable 5.2 specific guards.
    if family == "claude-fable-5-2":
        output_cfg = _subdict(req, "output_config") or _subdict(config, "output_config")
        reasoning = _subdict(req, "reasoning") or _subdict(config, "reasoning")
        found_effort, effort_raw = _lookup((output_cfg, thinking, reasoning, req, config), "effort")
        effort = str(effort_raw).strip().lower() if found_effort else None

        if effort == "max" and _is_multi_turn_loop(req, sess, harness, config):
            errors.append(
                _finding(
                    code="FABLE-MAX-EFFORT-LOOP",
                    severity="error",
                    message=(
                        "claude-fable-5-2 with effort='max' in a multi-turn loop triggers an "
                        "overthinking regression (ARC-AGI-3 79.26% -> 65.66%)."
                    ),
                    remediation="Cap claude-fable-5-2 multi-turn agent loops at effort='high' or 'xhigh'.",
                )
            )

        found_sub, subagents = _lookup(
            (harness, sess, req, config),
            "concurrent_subagents",
            "max_concurrent_subagents",
        )
        if found_sub and _is_number(subagents) and subagents > DEFAULT_FABLE_MAX_SUBAGENTS:
            errors.append(
                _finding(
                    code="FABLE-SUBAGENT-CAP",
                    severity="error",
                    message=(
                        f"claude-fable-5-2 concurrent_subagents ({subagents}) exceeds cap "
                        f"of {DEFAULT_FABLE_MAX_SUBAGENTS} [Heuristic]."
                    ),
                    remediation=(
                        f"Hard-cap concurrent_subagents to <= {DEFAULT_FABLE_MAX_SUBAGENTS} [Heuristic] "
                        "to prevent delegation runaway and cost spikes."
                    ),
                )
            )

        # CRITICAL: silent sticky downgrade / model_refusal_fallback.
        downgrade_triggers: List[str] = []
        found_stop, stop_reason = _lookup((resp, sess, config), "stop_reason")
        if found_stop and str(stop_reason).strip().lower() == "model_refusal_fallback":
            downgrade_triggers.append("stop_reason='model_refusal_fallback'")

        found_fb_flag, fb_flag = _lookup((resp, sess, harness, config), "model_refusal_fallback")
        if found_fb_flag and (fb_flag is True or (isinstance(fb_flag, str) and fb_flag.strip())):
            downgrade_triggers.append(f"model_refusal_fallback={fb_flag!r}")

        for m_key in ("response_model", "actual_model", "served_model", "fallback_model"):
            found_m, m_val = _lookup((resp, sess, harness, config), m_key)
            if found_m:
                m_norm = _normalize_model(m_val)
                if m_norm and FABLE_DOWNGRADE_RE.match(m_norm):
                    downgrade_triggers.append(f"{m_key}='{m_norm}'")

        if isinstance(config.get("response"), dict):
            resp_model = _normalize_model(config["response"].get("model"))
            if resp_model and FABLE_DOWNGRADE_RE.match(resp_model):
                downgrade_triggers.append(f"response.model='{resp_model}'")

        if downgrade_triggers:
            errors.append(
                _finding(
                    code="FABLE-SILENT-DOWNGRADE",
                    severity="critical",
                    message=(
                        "CRITICAL: claude-fable-5-2 triggered silent fallback/downgrade "
                        f"({', '.join(downgrade_triggers)}) to claude-opus-4-8 / claude-opus-5, "
                        "which increases prompt-injection risk."
                    ),
                    remediation=(
                        "Abort the session immediately, alert on-call/operator, and do not continue "
                        "the downgraded thread. Route security/cyber work to Opus 5.5 or Neon."
                    ),
                )
            )


def _validate_neon(
    config: Dict[str, Any],
    req: Dict[str, Any],
    resp: Dict[str, Any],
    sess: Dict[str, Any],
    harness: Dict[str, Any],
    errors: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
    strict: bool,
) -> None:
    gen_cfg = (
        _subdict(req, "generation_config", "generationConfig")
        or _subdict(config, "generation_config", "generationConfig")
    )
    think_cfg = (
        _subdict(gen_cfg, "thinking_config", "thinkingConfig")
        or _subdict(req, "thinking_config", "thinkingConfig")
        or _subdict(config, "thinking_config", "thinkingConfig")
    )
    usage = (
        _subdict(resp, "usage", "usage_metadata", "usageMetadata")
        or _subdict(config, "usage", "usage_metadata", "usageMetadata", "telemetry", "metrics")
    )
    telemetry = _subdict(config, "telemetry", "metrics") or _subdict(resp, "telemetry", "metrics")

    # 1. Legacy thinking_budget -> error
    found_budget, _ = _lookup((think_cfg, gen_cfg, req, config), "thinking_budget", "thinkingBudget")
    if found_budget:
        errors.append(
            _finding(
                code="NEON-LEGACY-THINKING-BUDGET",
                severity="error",
                message="gemini-4-neon rejects legacy 'thinking_budget' with HTTP 400.",
                remediation="Remove 'thinking_budget' and set 'thinking_level' (LOW, MEDIUM, HIGH, or XHIGH).",
            )
        )

    # 2. thinking_level validation (MINIMAL -> error; XHIGH on attempt 1 / LOW in multi-step -> warn)
    found_level, level_raw = _lookup((think_cfg, gen_cfg, req, config), "thinking_level", "thinkingLevel")
    level: Optional[str] = None
    if found_level:
        level = str(level_raw).strip().upper()
        if level == "MINIMAL":
            errors.append(
                _finding(
                    code="NEON-THINKING-LEVEL-MINIMAL",
                    severity="error",
                    message="gemini-4-neon rejects thinking_level='MINIMAL' with HTTP 400.",
                    remediation="Set thinking_level to one of: LOW, MEDIUM, HIGH, XHIGH (default: HIGH).",
                )
            )
        elif level not in NEON_VALID_LEVELS:
            errors.append(
                _finding(
                    code="NEON-THINKING-LEVEL-INVALID",
                    severity="error",
                    message=f"gemini-4-neon received unsupported thinking_level='{level_raw}'.",
                    remediation="Use one of: LOW, MEDIUM, HIGH, XHIGH.",
                )
            )

    # 3. Thought-signature preservation across multi-turn tool calls -> error
    found_pts, pts = _lookup((harness, sess, req, config), "preserve_thought_signatures")
    missing_sig = False
    if found_pts and pts is False:
        missing_sig = True
    else:
        # Inspect explicit contents/messages for model function_call parts lacking thought_signature.
        found_contents, contents = _lookup((req, sess, config), "contents", "messages")
        if found_contents and isinstance(contents, list):
            for turn in contents:
                if not isinstance(turn, dict):
                    continue
                role = str(turn.get("role", "")).strip().lower()
                if role not in ("model", "assistant"):
                    continue
                parts = turn.get("parts") or turn.get("content")
                if isinstance(parts, list):
                    for part in parts:
                        if not isinstance(part, dict):
                            continue
                        is_tool_call = any(
                            k in part for k in ("function_call", "functionCall", "tool_call", "toolCall")
                        ) or part.get("type") in ("function_call", "tool_call")
                        if is_tool_call:
                            sig = part.get("thought_signature") or part.get("thoughtSignature")
                            if not sig:
                                missing_sig = True
                                break
                if missing_sig:
                    break

    if missing_sig:
        errors.append(
            _finding(
                code="NEON-THOUGHT-SIGNATURES",
                severity="error",
                message=(
                    "gemini-4-neon multi-turn tool calls require thought-signature preservation "
                    "(preserve_thought_signatures must be true and tool-call parts must carry thought_signature)."
                ),
                remediation=(
                    "Set preserve_thought_signatures=true and echo verbatim thought_signature "
                    "fields on all prior model tool-call parts."
                ),
            )
        )

    # 4. Ignored sampling params: temperature, top_p, top_k (warning by default, error in --strict mode)
    ignored_found: List[str] = []
    for param, camel in (("temperature", "temperature"), ("top_p", "topP"), ("top_k", "topK")):
        found, _ = _lookup((gen_cfg, req, config), param, camel)
        if found:
            ignored_found.append(param)
    if ignored_found:
        severity = "error" if strict else "warning"
        target = errors if strict else warnings
        target.append(
            _finding(
                code="NEON-IGNORED-SAMPLING-PARAMS",
                severity=severity,
                message=(
                    f"gemini-4-neon silently ignores sampling parameter(s): {', '.join(ignored_found)}."
                ),
                remediation=(
                    "Remove temperature/top_p/top_k from Neon configs and do not rely on "
                    "temperature reduction as an anti-slop control."
                ),
            )
        )

    # 5. XHIGH on attempt 1 -> warning
    if level == "XHIGH":
        found_attempt, attempt = _lookup((harness, sess, req, config), "attempt", "attempt_number")
        found_retry, is_retry = _lookup((harness, sess, req, config), "is_retry", "after_test_failure")
        attempt_num = attempt if (found_attempt and _is_number(attempt)) else 1
        if not bool(is_retry) and attempt_num <= 1:
            warnings.append(
                _finding(
                    code="NEON-XHIGH-ATTEMPT-1",
                    severity="warning",
                    message=(
                        "gemini-4-neon thinking_level='XHIGH' on attempt 1 adds ~70% compute "
                        "and 50-57.5s TTFT for marginal (+1 pt) index gain."
                    ),
                    remediation="Start at thinking_level='HIGH' and escalate to 'XHIGH' only after a deterministic failure.",
                )
            )

    # 6. LOW in multi-step loop -> warning
    if level == "LOW" and _is_multi_turn_loop(req, sess, harness, config):
        warnings.append(
            _finding(
                code="NEON-LOW-MULTI-STEP",
                severity="warning",
                message="gemini-4-neon thinking_level='LOW' degrades multi-step consistency in agent loops.",
                remediation="Use thinking_level='HIGH' for multi-step loops ('MEDIUM' only for trivial single-pass edits).",
            )
        )

    # 7. Thinking-to-output token ratio > 4 [Heuristic] -> warning
    found_thoughts, thoughts_tok = _lookup(
        (usage, telemetry, resp, config), "thoughts_token_count", "thoughtsTokenCount"
    )
    found_cand, cand_tok = _lookup(
        (usage, telemetry, resp, config), "candidates_token_count", "candidatesTokenCount"
    )
    if found_thoughts and found_cand and _is_number(thoughts_tok) and _is_number(cand_tok):
        if cand_tok == 0 and thoughts_tok > 0:
            warnings.append(
                _finding(
                    code="NEON-THINKING-TOKEN-RATIO",
                    severity="warning",
                    message=(
                        f"gemini-4-neon emitted {thoughts_tok} thinking tokens with 0 candidate output tokens."
                    ),
                    remediation="Inspect reasoning-token bloat separately from final-answer length and cap effort.",
                )
            )
        elif cand_tok > 0 and (thoughts_tok / cand_tok) > DEFAULT_NEON_MAX_THOUGHT_RATIO:
            ratio = thoughts_tok / cand_tok
            warnings.append(
                _finding(
                    code="NEON-THINKING-TOKEN-RATIO",
                    severity="warning",
                    message=(
                        f"gemini-4-neon thoughts_token_count/candidates_token_count ratio ({ratio:.2f}:1) "
                        f"exceeds {DEFAULT_NEON_MAX_THOUGHT_RATIO:.0f}:1 [Heuristic]."
                    ),
                    remediation=(
                        "Check for hidden thinking-token bloat; step down from XHIGH to HIGH "
                        "or constrain task scope."
                    ),
                )
            )

    # 8. TTFT > 45s [Heuristic] -> warning
    found_ttft, ttft = _lookup((telemetry, usage, resp, config), "ttft_seconds", "ttftSeconds")
    if found_ttft and _is_number(ttft) and ttft > DEFAULT_NEON_MAX_TTFT_SECONDS:
        warnings.append(
            _finding(
                code="NEON-TTFT-HIGH",
                severity="warning",
                message=(
                    f"gemini-4-neon ttft_seconds ({ttft}s) exceeds "
                    f"{DEFAULT_NEON_MAX_TTFT_SECONDS:.0f}s [Heuristic]."
                ),
                remediation="Verify thinking_level (avoid XHIGH on attempt 1) and check prompt-cache hit rate.",
            )
        )

    # 9. Missing response_schema on structured/review calls -> warning
    found_task, task_raw = _lookup((harness, sess, req, config), "task_type", "workload", "task", "mode")
    found_struct, is_struct = _lookup((harness, sess, req, config), "structured", "is_structured", "is_review")
    needs_schema = bool(is_struct) if found_struct else False
    if found_task and isinstance(task_raw, str) and task_raw.strip().lower() in STRUCTURED_OR_REVIEW_MODES:
        needs_schema = True
    if needs_schema:
        found_schema, schema_val = _lookup(
            (gen_cfg, req, config), "response_schema", "responseSchema", "response_json_schema"
        )
        if not found_schema or not schema_val:
            warnings.append(
                _finding(
                    code="NEON-MISSING-RESPONSE-SCHEMA",
                    severity="warning",
                    message="gemini-4-neon structured/review call omits 'response_schema'.",
                    remediation=(
                        "Provide an explicit response_schema (e.g., auth/concurrency/boundary/deprecated_api "
                        "pass|fail|na fields with file:line) to curb slow non-adversarial reviews."
                    ),
                )
            )


def validate_config(config: Dict[str, Any], *, strict: bool = False) -> Dict[str, Any]:
    """Validate a 2026 model API/harness config dict.

    Returns {"ok": bool, "model": str | None, "errors": [...], "warnings": [...]}.
    Does not mutate the input dictionary.
    """
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    if not isinstance(config, dict):
        errors.append(
            _finding(
                code="API-CONFIG-TYPE",
                severity="error",
                message=f"Config must be a JSON object, got {type(config).__name__}.",
                remediation="Pass a dictionary / JSON object containing 'model' and request/harness fields.",
            )
        )
        return {"ok": False, "model": None, "errors": errors, "warnings": warnings}

    req = _subdict(config, "request") or config
    resp = _subdict(config, "response") or config
    sess = _subdict(config, "session") or config
    harness = _subdict(config, "harness") or config

    _, raw_model = _lookup((req, config, sess), "model", "model_id", "requested_model")
    model = _normalize_model(raw_model)
    if not model:
        errors.append(
            _finding(
                code="API-MODEL-MISSING",
                severity="error",
                message="Missing required 'model' identifier in config.",
                remediation=f"Set 'model' to one of: {', '.join(SUPPORTED_MODELS)}.",
            )
        )
        return {"ok": False, "model": None, "errors": errors, "warnings": warnings}

    family = _canonical_family(model)
    if family is None:
        errors.append(
            _finding(
                code="API-MODEL-UNKNOWN",
                severity="error",
                message=f"Unsupported model identifier '{model}'.",
                remediation=f"Use one of the 5 supported 2026 models: {', '.join(SUPPORTED_MODELS)}.",
            )
        )
        return {"ok": False, "model": model, "errors": errors, "warnings": warnings}

    if family in ("gpt-6.2-astra", "gpt-6.2-sol"):
        _validate_gpt62(family, config, req, sess, harness, errors, warnings)
    elif family in ("claude-opus-5-5", "claude-fable-5-2"):
        _validate_claude(family, config, req, resp, sess, harness, errors, warnings)
    elif family == "gemini-4-neon":
        _validate_neon(config, req, resp, sess, harness, errors, warnings, strict=strict)

    # Cross-model context-hygiene warning: lossy summarization alone obscures failure signals.
    ctx_dicts = (harness, sess, req, config)
    found_comp, comp_raw = _lookup(ctx_dicts, "compaction_strategy")
    if found_comp and isinstance(comp_raw, str):
        comp_norm = comp_raw.strip().lower().replace("-", "_")
        if (
            comp_norm == "summarize_only"
            and not _has_observation_masking(ctx_dicts)
            and not _has_checkpoint_reset(ctx_dicts)
        ):
            warnings.append(
                _finding(
                    code="HARNESS-LOSSY-SUMMARY-ONLY",
                    severity="warning",
                    message=(
                        f"{family} sets compaction_strategy='summarize_only' without observation masking "
                        "or checkpoint reset; lossy summarization alone obscures failure signals and "
                        "elongates failed trajectories (arXiv:2508.21433)."
                    ),
                    remediation=(
                        "Pair or replace lossy summarization with observation masking (observation_masking=true / "
                        "tool-result clearing) or explicit fresh checkpoint resets (checkpoint_reset=true)."
                    ),
                )
            )

    # Cross-family audit guard: catch correlated same-vendor authoring + auditing configs.
    primary_provider = _infer_provider_family(family)
    found_auditor_model, auditor_model_val = _lookup(
        ctx_dicts, "auditor_model", "reviewer_model", "verifier_model"
    )
    found_auditor_prov, auditor_prov_val = _lookup(
        ctx_dicts, "auditor_provider", "reviewer_provider", "verifier_provider"
    )
    auditor_provider = (
        _infer_provider_family(auditor_prov_val) if found_auditor_prov else None
    ) or (
        _infer_provider_family(auditor_model_val) if found_auditor_model else None
    )
    found_allow_same, allow_same_val = _lookup(ctx_dicts, "allow_same_family_audit")
    if (
        primary_provider is not None
        and auditor_provider is not None
        and auditor_provider == primary_provider
        and not bool(found_allow_same and allow_same_val)
    ):
        errors.append(
            _finding(
                code="HARNESS-SAME-FAMILY-AUDIT",
                severity="error",
                message=(
                    f"{family} ({primary_provider}) is configured with a same-family auditor/reviewer "
                    f"({auditor_model_val or auditor_prov_val}); own-family judges share correlated "
                    "blind spots (UK AISI EXT-04; Pombal et al. arXiv:2604.06996)."
                ),
                remediation=(
                    "Configure auditor_model / auditor_provider from a different vendor family "
                    "(Anthropic <-> OpenAI <-> Google) and run `anti-slop audit` in a clean-room context."
                ),
            )
        )

    # Claude ML R&D / local-inference routing warning: flag capability-cap & fallback risk when unverified.
    if family in ("claude-opus-5-5", "claude-fable-5-2"):
        found_wl, wl_raw = _lookup(ctx_dicts, "workload", "task_type", "mode")
        has_cross_auditor = (
            auditor_provider is not None
            and primary_provider is not None
            and auditor_provider != primary_provider
        )
        if (
            found_wl
            and isinstance(wl_raw, str)
            and wl_raw.strip().lower() in ML_RD_WORKLOADS
            and not has_cross_auditor
        ):
            warnings.append(
                _finding(
                    code="CLAUDE-ML-RD-CAP-WARNING",
                    severity="warning",
                    message=(
                        f"{family} declares workload='{wl_raw}' without a cross-family verifier; "
                        "Anthropic system cards document training-time capability caps on frontier AI R&D "
                        "and sticky fallback routing on dual-use triggers."
                    ),
                    remediation=(
                        "Pair ML/inference runs with Tier-1 `anti-slop verify` throughput/contract assertions "
                        "and configure a cross-family auditor (`auditor_provider != 'anthropic'`)."
                    ),
                )
            )

    return {
        "ok": len(errors) == 0,
        "model": model,
        "errors": errors,
        "warnings": warnings,
    }


def _load_json_configs(source: str) -> List[Tuple[str, Any]]:
    if source == "-":
        raw = sys.stdin.read()
        label = "<stdin>"
    else:
        path = Path(source)
        raw = path.read_text(encoding="utf-8")
        label = source

    data = json.loads(raw)
    if isinstance(data, list):
        return [(f"{label}[{idx}]", item) for idx, item in enumerate(data)]
    return [(label, data)]


def _format_human(source: str, result: Dict[str, Any]) -> str:
    lines: List[str] = []
    for item in result["errors"]:
        tag = item["severity"].upper()
        lines.append(f"{source}: [{tag}] {item['code']}: {item['message']}")
        lines.append(f"  remediation: {item['remediation']}")
    for item in result["warnings"]:
        lines.append(f"{source}: [WARNING] {item['code']}: {item['message']}")
        lines.append(f"  remediation: {item['remediation']}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate 2026 model API and harness configurations (Layer-1 gate)."
    )
    parser.add_argument(
        "configs",
        nargs="+",
        help="Path(s) to JSON config file(s), or '-' to read JSON from stdin.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit structured JSON results to stdout.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat silently ignored Neon sampling params (temperature/top_p/top_k) as errors.",
    )
    args = parser.parse_args(argv)

    all_errors: List[Dict[str, Any]] = []
    all_warnings: List[Dict[str, Any]] = []
    per_source: List[Dict[str, Any]] = []
    any_error = False

    for src in args.configs:
        try:
            entries = _load_json_configs(src)
        except (OSError, json.JSONDecodeError) as exc:
            err = _finding(
                code="API-CONFIG-LOAD",
                severity="error",
                message=f"Failed to load '{src}': {exc}",
                remediation="Provide a readable, valid JSON file.",
            )
            res = {"ok": False, "model": None, "errors": [err], "warnings": []}
            per_source.append({"source": src, **res})
            all_errors.append({**err, "source": src})
            any_error = True
            if not args.emit_json:
                print(_format_human(src, res), file=sys.stderr)
            continue

        for label, payload in entries:
            res = validate_config(payload, strict=args.strict)
            per_source.append({"source": label, **res})
            if not res["ok"]:
                any_error = True
            for e in res["errors"]:
                all_errors.append({**e, "source": label})
            for w in res["warnings"]:
                all_warnings.append({**w, "source": label})
            if not args.emit_json and (res["errors"] or res["warnings"]):
                print(_format_human(label, res), file=sys.stderr)

    if args.emit_json:
        if len(per_source) == 1:
            output = {
                "ok": per_source[0]["ok"],
                "model": per_source[0]["model"],
                "errors": per_source[0]["errors"],
                "warnings": per_source[0]["warnings"],
            }
        else:
            output = {
                "ok": not any_error,
                "errors": all_errors,
                "warnings": all_warnings,
                "results": per_source,
            }
        print(json.dumps(output, indent=2))

    return 1 if any_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
