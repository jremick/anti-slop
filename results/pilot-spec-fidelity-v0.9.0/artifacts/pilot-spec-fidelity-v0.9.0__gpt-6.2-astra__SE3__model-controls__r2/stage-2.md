# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:26:28Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 8.37
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

`compile_active_rules` now honors every user-declared field by default. It verifies all excerpts before applying `excluded_fields`, preserves remaining clauses in order, and drops the item if no clauses remain or if an exclusion matches with `drop_whole_item=True`. No hardcoded field exclusions remain.

`prepare_request` now uses `fast_tensor` without truncation for all accepted payloads. No hardcoded capacity caps or size-based fallbacks remain. Callers can set `max_prompt_bytes` to a positive integer and `max_tools` to a non-negative integer. Boolean, otherwise invalid, or exceeded bounds raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0`.

```text
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 93/120 (raw=94)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
