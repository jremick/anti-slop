# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:28:22Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: baseline
- Elapsed seconds: 7.62
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- The matcher honors every declared preference field by default. `excluded_fields` removes only matching clauses unless `drop_whole_item=True`. Every clause still undergoes excerpt verification. No hardcoded field exclusions remain.
- The runner routes accepted requests through `fast_tensor` without truncation. No hardcoded prompt or tool caps or size-based fallback remain. Callers can set `max_prompt_bytes` to a positive integer and `max_tools` to a non-negative integer. Invalid or exceeded bounds raise `ValueError`.

Verification passed. `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0` and reported `Ran 4 tests in 0.000s` and `OK`. Additional excerpt and explicit bound checks passed.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 88/120 (raw=90)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
