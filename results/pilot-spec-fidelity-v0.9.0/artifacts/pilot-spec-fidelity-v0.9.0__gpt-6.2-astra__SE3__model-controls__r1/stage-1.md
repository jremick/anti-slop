# pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:23:12Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 38.45
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

`matcher.py` now honors every declared preference field by default and verifies all excerpts before applying caller exclusions. An exclusion removes only matching clauses unless `drop_whole_item=True`. Items with no remaining clauses are omitted.

`runner.py` now routes valid requests through `fast_tensor` without truncation or internal size limits. Explicit limits still raise `ValueError` for invalid bounds or requests that exceed them.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited with code `0`. Its exact output was:

```text
test_caller_opt_in_excluded_fields_preserves_remaining_clauses (test_fidelity.SpecFidelityMatcherTests) ... ok
test_honors_skin_tone_ethnicity_and_paired_traits_by_default (test_fidelity.SpecFidelityMatcherTests) ... ok
test_explicit_caller_bounds_are_enforced (test_fidelity.SpecFidelityRunnerTests) ... ok
test_large_local_payload_runs_fast_tensor_without_hardcoded_caps (test_fidelity.SpecFidelityRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

Additional checks passed for invalid limit types, UTF-8 byte boundaries, a zero-tool limit, `hair_color`, and stale excerpts on excluded clauses.

## Blockers & Flaws

None.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-astra__SE3__model-controls__r1/stage-1-grader.json`): passed=True
