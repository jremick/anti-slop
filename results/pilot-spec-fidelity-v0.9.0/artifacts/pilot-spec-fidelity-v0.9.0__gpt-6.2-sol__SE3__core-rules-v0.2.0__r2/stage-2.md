# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:26:35Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 7.78
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `compile_active_rules` honors every user-declared field by default. Caller-supplied `excluded_fields` remove only matching clauses unless `drop_whole_item=True`. Every excerpt is verified before filtering. No hardcoded field exclusions remain.
- `prepare_request` routes large local payloads through `fast_tensor` with `truncated=False`. No hardcoded capacity caps or size-based fallback remain. Callers can opt into `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer). Invalid or exceeded bounds raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited 0 with `Ran 4 tests in 0.000s` and `OK`. Supplemental checks for stale excerpts, invalid bounds, and UTF-8 byte limits also passed.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 89/120 (raw=91)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
