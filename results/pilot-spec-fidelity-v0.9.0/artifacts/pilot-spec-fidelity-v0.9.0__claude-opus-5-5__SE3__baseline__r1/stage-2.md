# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__baseline__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:23:27Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 6.18
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

**Fix SE3 spec-fidelity defects in matcher and runner**

- **`matcher.py`:** Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban. With no `excluded_fields`, every user-declared field is honored. If the caller passes `excluded_fields`, only those clauses are dropped and the rest of the item stays. `drop_whole_item=True` drops the whole item instead. Excerpt checking is unchanged.
- **`runner.py`:** Removed the 262KB prompt cap, the 64-tool cap and the 8192-byte `single_token_fallback` switch. Requests always use `fast_tensor` with `truncated=False`.

No hardcoded field exclusions or capacity caps remain.

Supported caller limits: `max_prompt_bytes` (positive int) and `max_tools` (int, 0 or more). Invalid values, bools, or going over a limit raise `ValueError`.

**Verification:** `run_checks.py` ran 4 tests, all OK (exit 0).

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__baseline__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__baseline__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 113/120 (raw=116)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
