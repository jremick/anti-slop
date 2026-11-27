# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:35:49Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 18.75
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

## Summary
- **`matcher.py`**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors all user-declared preference fields by default while preserving verbatim `source_excerpt` verification. Added opt-in `excluded_fields` filtering to drop only excluded clauses (or the whole source item when `drop_whole_item=True`).
- **`runner.py`**: Removed the hardcoded 262 KB prompt cap, 64-tool cap, and 8,192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads on `execution_mode="fast_tensor"` with `truncated=False` when bounds are unset.

No hardcoded field exclusions or internal capacity caps remain. Supported caller opt-in bounds: `excluded_fields` (with `drop_whole_item`) in `compile_active_rules`, and validated `max_prompt_bytes` (`> 0` int) and `max_tools` (`>= 0` int) in `prepare_request`.

## Verification
- `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`: `Ran 4 tests in 0.000s` — `OK`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 104/120 (raw=112)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
