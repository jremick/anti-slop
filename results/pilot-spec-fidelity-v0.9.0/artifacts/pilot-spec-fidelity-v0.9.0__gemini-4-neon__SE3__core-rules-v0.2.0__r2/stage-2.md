# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:34:05Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 18.13
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

Fix two spec-fidelity defects in `benchmarks/sources/se3_spec_fidelity/` (standard library only):

- **`matcher.py` (`compile_active_rules`)**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban while preserving verbatim excerpt verification. Added caller opt-in `excluded_fields` filtering (clause-level by default; full-item drop with `drop_whole_item=True`).
- **`runner.py` (`prepare_request`)**: Removed hardcoded 262KB prompt, 64-tool, and 8192-byte `single_token_fallback` limits so arbitrary local payloads run on `execution_mode="fast_tensor"` with `truncated=False`. Added strict `ValueError` validation and enforcement for opt-in `max_prompt_bytes` (strictly positive `int`, non-`bool`) and `max_tools` (non-negative `int`, non-`bool`).

No hardcoded field exclusions or capacity caps remain.

**Verification:** `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` passed (`Ran 4 tests`, `OK`, exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 91/120 (raw=93)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
