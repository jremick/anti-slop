# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:29:17Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 7.54
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `matcher.py` honors all declared preference fields by default. It verifies every excerpt before applying `excluded_fields`, which removes only matching clauses by default. Setting `drop_whole_item=True` drops any item containing an excluded field. No hardcoded field exclusions remain.
- `runner.py` routes accepted payloads through `fast_tensor` without truncation. No hardcoded capacity caps or size-based fallback remain. Callers can opt into `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer). Invalid limits and exceeded bounds raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0`: `Ran 4 tests in 0.001s`, `OK`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 84/120 (raw=86)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
