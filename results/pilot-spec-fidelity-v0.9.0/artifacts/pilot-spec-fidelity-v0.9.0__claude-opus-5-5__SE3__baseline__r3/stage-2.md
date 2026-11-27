# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__baseline__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:27:49Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 6.29
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

## Restore spec fidelity in matcher and runner

**`matcher.py`:** Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) exclusion. When `excluded_fields` is `None`, every field the user declared is kept. Excluding fields is now caller opt-in: only the excluded clauses are removed, and the whole item is dropped only with `drop_whole_item=True`. Excerpt verification is unchanged.

**`runner.py`:** Removed the 262KB prompt cap, the 64-tool cap and the 8192-byte `single_token_fallback` downgrade. Requests always run on `fast_tensor`.

No hardcoded field exclusions or capacity caps remain. Callers can still set `max_prompt_bytes` (positive int) and `max_tools` (non-negative int); invalid values or going over a limit raise `ValueError`.

**Verification:** `run_checks.py` ran 4 tests: OK, exit code 0.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__baseline__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__baseline__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 110/120 (raw=112)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
