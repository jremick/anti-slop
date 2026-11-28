# pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:45:35Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: baseline
- Elapsed seconds: 150.70
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

Implemented [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py) and [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py) using only the Python standard library according to [SPEC.md](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/SPEC.md), without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`.

### Summary of Implementation
- **`compile_preference_rules`** in [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py):
  - Validates `items` (`Mapping`), `clauses` (`Sequence`, excluding `str`/`bytes`/`bytearray`), `excluded_fields` (`None` or `Collection` of non-empty strings, excluding `str`/`bytes`/`bytearray`), and `drop_whole_item` (`bool`), raising `ValueError` on violations.
  - Groups clauses by `source_id` preserving first-seen source and clause order, parses base-10 integer IDs safely, skips unparseable or missing source IDs, and runs verbatim non-empty `source_excerpt` verification before exclusion filtering (skipping the whole source group on any stale clause).
  - Applies zero field exclusions when `excluded_fields is None`, and honors `drop_whole_item` when `excluded_fields` is provided.
- **`prepare_inference_batch`** in [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py):
  - Validates `prompt_text`, `tools` (and each element), `force_mode`, `max_prompt_bytes` (strictly positive `int`, rejecting `bool`), and `max_tools` (non-negative `int`, rejecting `bool`).
  - Computes UTF-8 byte length and tool count, leaves both unbounded by default (`None`), enforces opt-in bounds, routes to `"fast_tensor"` unless `force_mode` is explicitly set, and always returns `truncated=False`.

### Exact Result of `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`
Exit code: `0`

```text
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r1/stage-1-grader.json`): passed=True
