# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:26:20Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 36.02
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

`matcher.py` now honors every user-declared field by default and verifies every excerpt before applying caller exclusions. An exclusion removes only matching clauses unless `drop_whole_item=True` or no clauses remain.

`runner.py` now routes accepted requests through `fast_tensor` without truncation. Only caller-supplied limits apply. Invalid or exceeded limits raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0`. Its exact summary was:

```text
Ran 4 tests in 0.000s

OK
```

Additional checks passed for UTF-8 byte limits, zero-tool limits, invalid limit types, and stale excerpts in excluded clauses.

## Blockers & Flaws

None.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r2/stage-1-grader.json`): passed=True
