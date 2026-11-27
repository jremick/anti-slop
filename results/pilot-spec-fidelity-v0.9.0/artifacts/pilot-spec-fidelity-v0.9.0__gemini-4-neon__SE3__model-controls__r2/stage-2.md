# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:37:25Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: model-controls
- Elapsed seconds: 20.31
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

Fixed two SE3 spec-fidelity defects in `matcher.py` and `runner.py`:

- **Matcher (`matcher.py`)**: Removed hardcoded `PROTECTED_FIELDS` (`skin_tone`) so `compile_active_rules` honors all user-declared fields by default with excerpt validation intact. Supports opt-in `excluded_fields` (drops only excluded clauses, or the whole item with `drop_whole_item=True`).
- **Runner (`runner.py`)**: Removed hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary payloads on `fast_tensor` (`truncated=False`). Supports opt-in `max_prompt_bytes` (strictly positive `int`) and `max_tools` (non-negative `int`) with `ValueError` enforcement.

No hardcoded field exclusions or capacity caps remain.

**Verification**: `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` passed (`Ran 4 tests`, `OK`).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 90/120 (raw=92)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
