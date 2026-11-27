# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:42:10Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 19.73
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

**Spec-fidelity fixes for `se3_spec_fidelity`**

- **`matcher.py`**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors all user-declared preference fields by default with verbatim excerpt verification intact. Added opt-in `excluded_fields` filtering that drops only matching clauses while preserving remaining valid clauses (dropping the whole item only when `drop_whole_item=True` or empty).
- **`runner.py`**: Removed the hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes unbounded local payloads on `fast_tensor` with `truncated=False`.

No hardcoded field exclusions or capacity caps remain. Supported caller opt-in bounds: `excluded_fields`/`drop_whole_item`, `max_prompt_bytes` (positive int), and `max_tools` (non-negative int).

**Verification:** `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` passed (`Ran 4 tests in 0.000s`, `OK`, exit code 0).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 104/120 (raw=106)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
