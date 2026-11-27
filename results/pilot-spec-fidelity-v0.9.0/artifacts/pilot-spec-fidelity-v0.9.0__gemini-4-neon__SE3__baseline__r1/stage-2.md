# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:31:07Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 20.71
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

### Summary
- **`matcher.py` (`compile_active_rules`)**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so all user-declared preference fields are honored by default while preserving verbatim excerpt validation. Added explicit caller opt-in filtering via `excluded_fields` (drops only excluded clauses by default, or the whole item with `drop_whole_item=True`).
- **`runner.py` (`prepare_request`)**: Removed hardcoded 262KB prompt, 64-tool, and 8192-byte `single_token_fallback` limits so arbitrary payloads route on `execution_mode="fast_tensor"` with `truncated=False` by default. Enforced explicit opt-in caller bounds (`max_prompt_bytes` > 0, `max_tools` >= 0; non-bool `int` with `ValueError`).

No hardcoded field exclusions or capacity caps remain.

### Verification
`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` — Ran 4 tests in 0.000s, **OK** (exit code 0).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 96/120 (raw=103)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
