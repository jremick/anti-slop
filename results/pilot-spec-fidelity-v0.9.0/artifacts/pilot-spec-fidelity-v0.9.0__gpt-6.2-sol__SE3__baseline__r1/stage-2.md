# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:24:31Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: baseline
- Elapsed seconds: 7.58
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `matcher.py` honors every user-declared preference field by default. Caller-supplied `excluded_fields` removes matching clauses, and `drop_whole_item=True` drops any source containing an excluded field. Verbatim excerpt verification still applies to every clause before filtering.
- `runner.py` routes local requests through `fast_tensor` without truncation. Callers can opt into a positive integer `max_prompt_bytes` limit and a non-negative integer `max_tools` limit. Invalid or exceeded limits raise `ValueError`.
- No hardcoded field exclusions, capacity caps, or size-based fallbacks remain.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0` and reported `Ran 4 tests in 0.000s` and `OK`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__baseline__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 84/120 (raw=87)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
