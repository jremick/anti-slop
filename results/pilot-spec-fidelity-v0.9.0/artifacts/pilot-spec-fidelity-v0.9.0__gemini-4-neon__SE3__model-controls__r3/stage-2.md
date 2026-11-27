# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:38:54Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: model-controls
- Elapsed seconds: 24.18
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

### Summary
Fixed two spec-fidelity defects in `benchmarks/sources/se3_spec_fidelity`:

- **`matcher.py`**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors all user-declared fields while keeping verbatim excerpt verification. Supported opt-in `excluded_fields` filtering (drops only excluded clauses by default, or the whole item with `drop_whole_item=True`).
- **`runner.py`**: Removed hardcoded 262 KB prompt and 64-tool caps and `single_token_fallback`, routing payloads on `execution_mode="fast_tensor"` (`truncated=False`). Enforced strict `ValueError` validation for opt-in `max_prompt_bytes` (positive `int`, non-`bool`) and `max_tools` (non-negative `int`, non-`bool`).

No hardcoded field exclusions or capacity caps remain.

### Verification
`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` passed (`Ran 4 tests in 0.000s`, `OK`, exit code 0).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 93/120 (raw=97)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
