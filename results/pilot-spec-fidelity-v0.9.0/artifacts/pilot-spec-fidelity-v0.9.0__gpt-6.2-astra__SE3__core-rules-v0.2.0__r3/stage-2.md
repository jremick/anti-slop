# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:28:02Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 8.07
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `compile_active_rules` honors every user-declared field by default. No hardcoded field exclusions remain. It verifies every excerpt before applying `excluded_fields`, preserves remaining clauses in order, and drops the item if no clauses remain or `drop_whole_item=True` matches an excluded field.
- `prepare_request` routes all accepted payloads through `fast_tensor` without truncation. No hardcoded prompt-size or tool-count caps remain. Callers can set `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer). Invalid bounds, including booleans, and exceeded limits raise `ValueError`.
- Verification: `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0`. `Ran 4 tests in 0.000s` — `OK`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__core-rules-v0.2.0__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 88/120 (raw=92)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
