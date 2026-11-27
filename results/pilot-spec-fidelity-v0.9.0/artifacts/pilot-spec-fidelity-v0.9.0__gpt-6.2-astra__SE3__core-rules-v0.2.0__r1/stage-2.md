# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:24:13Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 8.31
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

`compile_active_rules` now honors every user-declared preference field by default. It verifies all excerpts before filtering. Caller-supplied `excluded_fields` removes matching clauses and skips empty items. With `drop_whole_item=True`, any matching clause drops the entire item. No hardcoded field exclusions remain.

`prepare_request` now routes all accepted payloads through `fast_tensor` without truncation. No hardcoded capacity caps or size-based fallback remain. Callers can set `max_prompt_bytes` to a positive integer and `max_tools` to a non-negative integer. Booleans, other invalid bounds, and exceeded limits raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0`.

```text
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 92/120 (raw=93)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
