# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:24:59Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 8.86
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

`compile_active_rules` honors every user-declared preference field by default. It verifies all source excerpts before filtering. Caller-supplied `excluded_fields` removes only matching clauses, skips items with no remaining clauses, and drops an entire matching item when `drop_whole_item=True`. No hardcoded field exclusions remain.

`prepare_request` routes accepted payloads through `fast_tensor` without truncation, hardcoded capacity caps, or size-based fallback. Callers can set `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer) independently. Boolean, invalid, or exceeded bounds raise `ValueError`.

Verification with `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0`:

```text
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 89/120 (raw=90)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
