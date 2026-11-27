# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:35:30Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: baseline
- Elapsed seconds: 85.32
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

Fixed both spec-fidelity defects in [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/matcher.py) and [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/runner.py):

- **[matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/matcher.py#L30-L77)**:
  - Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) exclusion so `compile_active_rules` honors every user-declared preference field when `excluded_fields` is `None`.
  - Preserved verbatim non-empty `source_excerpt` verification across all clauses in each source group.
  - Added opt-in `excluded_fields` handling: drops only clauses whose `field` is in `excluded_fields` (skipping the source only if no clauses remain), or drops the whole source group when `drop_whole_item=True`.
- **[runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/runner.py#L24-L64)**:
  - Removed hardcoded `DEFAULT_MAX_PROMPT_BYTES` (262,144), `DEFAULT_MAX_TOOLS` (64), and `FAST_PATH_BYTE_CUTOFF` (8,192) / `single_token_fallback` downgrade so arbitrary payloads route on `execution_mode="fast_tensor"` with `truncated=False` when bounds are `None`.
  - Added strict validation and `ValueError` enforcement when `max_prompt_bytes` (strictly positive `int`, rejecting `bool`) or `max_tools` (non-negative `int`, rejecting `bool`) is explicitly provided.

### Verification

Result of running `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` ([run_checks.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/run_checks.py)):

```text
test_caller_opt_in_excluded_fields_preserves_remaining_clauses (test_fidelity.SpecFidelityMatcherTests) ... ok
test_honors_skin_tone_ethnicity_and_paired_traits_by_default (test_fidelity.SpecFidelityMatcherTests) ... ok
test_explicit_caller_bounds_are_enforced (test_fidelity.SpecFidelityRunnerTests) ... ok
test_large_local_payload_runs_fast_tensor_without_hardcoded_caps (test_fidelity.SpecFidelityRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__baseline__r2/stage-1-grader.json`): passed=True
