# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:27:15Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 8.41
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `compile_active_rules` honors every user-declared field by default. No hardcoded field exclusions remain. It verifies all excerpts before applying `excluded_fields`, preserves remaining clauses, and skips items with no clauses left. With `drop_whole_item=True`, any excluded clause drops its item.
- `prepare_request` routes all accepted payloads through `fast_tensor` without truncation. No hardcoded capacity caps or size-based fallback remain. Callers can set `max_prompt_bytes` to a positive integer and `max_tools` to a non-negative integer. Invalid bounds, including booleans, and exceeded bounds raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code 0.

```text
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 90/120 (raw=93)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
