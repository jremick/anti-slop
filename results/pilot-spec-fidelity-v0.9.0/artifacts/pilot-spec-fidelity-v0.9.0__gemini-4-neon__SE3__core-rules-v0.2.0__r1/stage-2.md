# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:29:28Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 18.35
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

## Summary
- **`matcher.py`**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors all user-declared fields while keeping verbatim excerpt verification intact. Added opt-in `excluded_fields` filtering (drops only excluded clauses by default, or the entire source when `drop_whole_item=True`).
- **`runner.py`**: Removed hardcoded 262 KB prompt, 64-tool, and 8192-byte `single_token_fallback` limits so `prepare_request` routes arbitrary local payloads on `fast_tensor` (`truncated=False`) by default.

No hardcoded field exclusions, capacity caps, or fallback ceilings remain. Supported opt-in caller bounds/controls: `excluded_fields` (with `drop_whole_item`), `max_prompt_bytes` (strictly positive `int`), and `max_tools` (non-negative `int`), enforced with `ValueError`.

## Verification
`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` — `Ran 4 tests in 0.000s`, `OK` (exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 98/120 (raw=103)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
