# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:30:15Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 7.55
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- The matcher honors all declared preference fields by default. `excluded_fields` removes only matching clauses unless `drop_whole_item=True`. Excerpt verification still applies to every clause before filtering.
- The runner routes large local payloads through `fast_tensor` with `truncated=False`. No hardcoded field exclusions, capacity caps, or size-triggered fallbacks remain. Callers can opt into a positive integer UTF-8 `max_prompt_bytes` limit and a non-negative integer `max_tools` limit. Invalid or exceeded limits raise `ValueError`.
- `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited 0 with `Ran 4 tests in 0.000s` and `OK`. Additional edge checks passed.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 83/120 (raw=86)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
