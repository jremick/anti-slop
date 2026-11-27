# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:27:16Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 5.63
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

**SE3 spec-fidelity: remove hardcoded field ban and capacity caps**

- `matcher.py`: Removed the `PROTECTED_FIELDS` (`skin_tone`) ban, so every user-declared field is kept by default. Added caller opt-in `excluded_fields`, which drops only the excluded clauses; `drop_whole_item=True` drops the whole item. Excerpt verification is unchanged.
- `runner.py`: Removed the 262KB prompt cap, the 64-tool cap and the 8192-byte `single_token_fallback`. Requests now always use `fast_tensor`.

No hardcoded field exclusions or capacity caps remain.

Caller limits: `max_prompt_bytes` (positive int) and `max_tools` (non-negative int). Bad values and exceeded limits raise `ValueError`.

Verification: `run_checks.py` ran 4 tests and printed `OK` (exit 0); before the fix it failed 3 of 4. Test files are unchanged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 110/120 (raw=113)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
