# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:24:43Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 6.27
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

**SE3 spec-fidelity fixes**

- `matcher.py`: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban. Every declared field is now honored when `excluded_fields=None`. Exclusions are opt-in: only excluded clauses are dropped, unless `drop_whole_item=True` drops the whole item. Excerpt verification is unchanged.
- `runner.py`: Removed the 262,144-byte prompt cap, the 64-tool cap and the 8,192-byte `single_token_fallback` downgrade. Requests without caller limits route to `fast_tensor`, untruncated.

No hardcoded field exclusions or size caps remain. Supported caller limits: `max_prompt_bytes` (positive int) and `max_tools` (non-negative int). Both reject bools and raise `ValueError` when exceeded.

Verification: `run_checks.py` ran 4 tests, all OK (exit 0). Edge cases were also checked by hand.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 104/120 (raw=107)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
