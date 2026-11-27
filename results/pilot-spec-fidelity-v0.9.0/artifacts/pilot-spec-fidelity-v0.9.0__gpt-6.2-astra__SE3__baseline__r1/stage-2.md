# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__baseline__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:22:32Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: baseline
- Elapsed seconds: 8.71
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `compile_active_rules` honors every user-declared field by default. No hardcoded field exclusions remain. It verifies all excerpts before applying `excluded_fields`, preserves remaining clauses, and drops the source if none remain or `drop_whole_item=True` matches an excluded field.
- `prepare_request` uses `fast_tensor` without truncation, including for prompts over 1 MB and more than 70 tools. No hardcoded capacity caps or size-based fallback remain. Callers can set `max_prompt_bytes` to a positive integer and `max_tools` to a nonnegative integer. Boolean, invalid, or exceeded bounds raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0`.

```text
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__baseline__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__baseline__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 93/120 (raw=96)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
