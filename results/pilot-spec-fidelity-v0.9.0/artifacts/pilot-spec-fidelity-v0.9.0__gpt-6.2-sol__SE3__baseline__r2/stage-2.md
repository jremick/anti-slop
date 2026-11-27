# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:27:26Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: baseline
- Elapsed seconds: 7.46
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `matcher.py` honors all declared preference fields by default. Caller-provided `excluded_fields` removes only matching clauses unless `drop_whole_item=True`. Excerpt verification still applies to every clause before filtering.
- `runner.py` routes accepted requests through `fast_tensor` without truncation. Callers can opt into `max_prompt_bytes` (a positive integer counting UTF-8 bytes) and `max_tools` (a non-negative integer). Invalid or exceeded bounds raise `ValueError`.
- No hardcoded field exclusions or capacity caps remain in either module.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0` and reported `Ran 4 tests in 0.000s` followed by `OK`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 82/120 (raw=85)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
