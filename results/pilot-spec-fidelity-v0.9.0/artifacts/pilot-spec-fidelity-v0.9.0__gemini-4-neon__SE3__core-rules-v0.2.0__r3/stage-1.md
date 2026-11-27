# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r3 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:40:15Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 81.33
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

Fixed both spec-fidelity defects in `benchmarks/sources/se3_spec_fidelity/` using only the Python standard library:

- **[matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/matcher.py)**:
  - Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) exclusion so `compile_active_rules` honors every user-declared preference field when `excluded_fields` is `None` (or empty).
  - Kept stale-compile excerpt validation on every clause in each source group (`isinstance(source_excerpt, str)`, non-empty, verbatim substring of `item.statement`).
  - Implemented opt-in `excluded_fields` filtering: drops only excluded clauses and keeps remaining valid clauses (skipping the source only if none remain), or drops the whole source group when `drop_whole_item=True`.

- **[runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/runner.py)**:
  - Removed the hardcoded `DEFAULT_MAX_PROMPT_BYTES` (262,144), `DEFAULT_MAX_TOOLS` (64), and `FAST_PATH_BYTE_CUTOFF` (8,192) `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads on `execution_mode="fast_tensor"` with `truncated=False` when `max_prompt_bytes` and `max_tools` are `None`.
  - Added strict validation for opt-in caller bounds (`max_prompt_bytes` must be a strictly positive non-bool `int`; `max_tools` must be a non-negative non-bool `int`) and preserved `ValueError` enforcement when either bound is exceeded.

### Verification

Initial run of `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` failed with 2 failures and 1 error (`FAILED (failures=2, errors=1)`).

Re-running `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` after the fixes exited with code `0`:

```text
test_caller_opt_in_excluded_fields_preserves_remaining_clauses (test_fidelity.SpecFidelityMatcherTests) ... ok
test_honors_skin_tone_ethnicity_and_paired_traits_by_default (test_fidelity.SpecFidelityMatcherTests) ... ok
test_explicit_caller_bounds_are_enforced (test_fidelity.SpecFidelityRunnerTests) ... ok
test_large_local_payload_runs_fast_tensor_without_hardcoded_caps (test_fidelity.SpecFidelityRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

Additional inline assertions also verified docstring edge cases (stale excerpt on excluded clauses, empty/None excerpts, empty `excluded_fields`, bool/non-int/zero/negative bounds, multibyte UTF-8 byte counting, and exact boundary acceptance).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r3/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r3/stage-1-grader.json`): passed=True
