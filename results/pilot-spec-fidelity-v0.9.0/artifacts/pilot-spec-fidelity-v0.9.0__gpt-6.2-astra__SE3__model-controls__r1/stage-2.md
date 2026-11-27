# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:23:21Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 9.18
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

`compile_active_rules` honors every user-declared field by default. No hardcoded field exclusions remain. It verifies every source excerpt before applying `excluded_fields`. By default, it removes only matching clauses and skips items with no clauses left. With `drop_whole_item=True`, any matching clause drops the item.

`prepare_request` routes valid local payloads through `fast_tensor` without truncation, hardcoded capacity caps, or a size-based fallback. Callers can set `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer). Boolean, invalid, or exceeded bounds raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0`.

```text
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 92/120 (raw=93)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
