# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:32:30Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: model-controls
- Elapsed seconds: 17.65
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

### Spec-Fidelity Fixes

- **`matcher.py` (`compile_active_rules`)**: Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so all user-declared preference fields are honored by default while keeping verbatim non-empty `source_excerpt` verification intact. Implemented opt-in `excluded_fields` filtering that drops only excluded clauses (retaining remaining valid clauses) or the whole source when `drop_whole_item=True`.
- **`runner.py` (`prepare_request`)**: Removed the hardcoded 262 KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so unbounded requests always route on `execution_mode="fast_tensor"` with `truncated=False`.

No hardcoded field exclusions or capacity caps remain. Supported caller opt-in bounds: `excluded_fields` (with `drop_whole_item`), `max_prompt_bytes` (positive non-bool `int`), and `max_tools` (non-negative non-bool `int`), enforcing `ValueError` on violations.

**Verification:** `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` — 4/4 tests OK (exit code 0).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 106/120 (raw=110)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
