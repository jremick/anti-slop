# pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:32:13Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: model-controls
- Elapsed seconds: 65.73
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

Fixed both spec-fidelity defects using the Python standard library only:

- [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/matcher.py#L30-L77): Removed the hardcoded `PROTECTED_FIELDS` exclusion so `compile_active_rules` preserves all user-declared fields by default, retained verbatim non-empty `source_excerpt` verification per source, and implemented opt-in `excluded_fields` filtering (dropping only excluded clauses and keeping remaining valid clauses, or dropping the whole source when `drop_whole_item=True` or no clauses remain).
- [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se3_spec_fidelity/runner.py#L24-L64): Removed `DEFAULT_MAX_PROMPT_BYTES`, `DEFAULT_MAX_TOOLS`, and `FAST_PATH_BYTE_CUTOFF` (`single_token_fallback`) so `prepare_request` routes arbitrary local payloads on `execution_mode="fast_tensor"` with `truncated=False` when bounds are `None`, while strictly validating explicit `max_prompt_bytes` (strictly positive non-bool `int`) and `max_tools` (non-negative non-bool `int`) and raising `ValueError` on violations.

### Verification (`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`)

```text
test_caller_opt_in_excluded_fields_preserves_remaining_clauses (test_fidelity.SpecFidelityMatcherTests) ... ok
test_honors_skin_tone_ethnicity_and_paired_traits_by_default (test_fidelity.SpecFidelityMatcherTests) ... ok
test_explicit_caller_bounds_are_enforced (test_fidelity.SpecFidelityRunnerTests) ... ok
test_large_local_payload_runs_fast_tensor_without_hardcoded_caps (test_fidelity.SpecFidelityRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

Exit code: `0`. Additional ad-hoc edge-case assertions (stale excerpts, empty `excluded_fields`, `bool`/zero/negative bounds, UTF-8 byte limits) also passed.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gemini-4-neon__SE3__model-controls__r1/stage-1-grader.json`): passed=True
