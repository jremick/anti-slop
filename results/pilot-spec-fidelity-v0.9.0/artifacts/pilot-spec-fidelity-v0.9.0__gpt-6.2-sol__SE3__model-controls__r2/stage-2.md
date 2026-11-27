# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:25:37Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 9.78
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `matcher.py` honors all declared preference fields by default. Caller-supplied `excluded_fields` removes matching clauses and preserves the rest. With `drop_whole_item=True`, any matching exclusion drops the entire item. Excerpt verification still applies to every clause in the source.
- `runner.py` uses `fast_tensor` for all valid requests. Callers can set `max_prompt_bytes` to a positive integer and `max_tools` to a non-negative integer. Invalid or exceeded bounds raise `ValueError`.

Zero hardcoded field exclusions or capacity caps remain. `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0` with `Ran 4 tests in 0.000s` and `OK`. Additional excerpt, UTF-8 byte limit, and invalid-bound checks passed.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 92/120 (raw=94)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
