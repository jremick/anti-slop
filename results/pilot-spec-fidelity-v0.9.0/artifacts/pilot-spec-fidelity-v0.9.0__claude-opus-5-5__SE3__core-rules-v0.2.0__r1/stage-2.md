# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:24:05Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 6.14
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

**Fix SE3 spec-fidelity defects in matcher and runner**

- **`matcher.py`:** Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban, so every declared preference field is honored by default. Excerpt verification is unchanged.
- **`runner.py`:** Removed the 262,144-byte prompt cap, 64-tool cap and 8,192-byte `single_token_fallback` downgrade. Requests without caller bounds always use `fast_tensor`.

No hardcoded field exclusions or capacity caps remain.

**Caller opt-in bounds:** `excluded_fields` drops only excluded clauses, or whole items with `drop_whole_item=True`. `max_prompt_bytes` (positive int) and `max_tools` (non-negative int) are validated and raise `ValueError` when exceeded.

**Verification:** `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` reports `Ran 4 tests`, `OK`, exit 0. Edge cases were also checked manually.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 102/120 (raw=105)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
