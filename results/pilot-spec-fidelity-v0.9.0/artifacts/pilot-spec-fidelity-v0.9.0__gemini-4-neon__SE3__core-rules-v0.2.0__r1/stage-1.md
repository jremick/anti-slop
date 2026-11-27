# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:29:10Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 80.28
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
  - Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors all user-declared fields when `excluded_fields` is `None`.
  - Preserved verbatim non-empty `source_excerpt` validation against `item.statement` across all clauses in a source group.
  - Added caller opt-in `excluded_fields` filtering: when `drop_whole_item=True`, drops any source containing an excluded field; when `drop_whole_item=False` (default), removes only excluded clauses and keeps the remaining valid clauses (skipping the source only if none remain).
- **[runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/runner.py)**:
  - Removed `DEFAULT_MAX_PROMPT_BYTES` (262,144), `DEFAULT_MAX_TOOLS` (64), and `FAST_PATH_BYTE_CUTOFF` (8,192) / `single_token_fallback` downgrade so `prepare_request` accepts arbitrary local prompts and tool counts on `execution_mode="fast_tensor"` with `truncated=False` when `max_prompt_bytes` and `max_tools` are `None`.
  - Added strict `ValueError` validation and bound checks whenever `max_prompt_bytes` (strictly positive `int`, rejecting `bool` and `<= 0`) or `max_tools` (non-negative `int`, rejecting `bool` and `< 0`) is explicitly supplied.

### Verification

Result of `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` ([run_checks.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/run_checks.py)) — exit code `0`:

```text
test_caller_opt_in_excluded_fields_preserves_remaining_clauses (test_fidelity.SpecFidelityMatcherTests) ... ok
test_honors_skin_tone_ethnicity_and_paired_traits_by_default (test_fidelity.SpecFidelityMatcherTests) ... ok
test_explicit_caller_bounds_are_enforced (test_fidelity.SpecFidelityRunnerTests) ... ok
test_large_local_payload_runs_fast_tensor_without_hardcoded_caps (test_fidelity.SpecFidelityRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

Also verified additional docstring edge cases (empty/stale excerpts, empty `excluded_fields`, invalid `prompt_text`, `bool`/negative/zero bounds for `max_prompt_bytes` and `max_tools`, UTF-8 multi-byte prompt sizing, and `fast_tensor` preservation for large explicitly bounded prompts).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__core-rules-v0.2.0__r1/stage-1-grader.json`): passed=True
