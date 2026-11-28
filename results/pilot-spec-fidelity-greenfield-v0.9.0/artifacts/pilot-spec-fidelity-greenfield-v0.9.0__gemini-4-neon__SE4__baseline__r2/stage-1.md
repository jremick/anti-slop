# pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:57:04Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: baseline
- Elapsed seconds: 124.85
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

Implemented [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py) and [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py) using only the Python standard library per [SPEC.md](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/SPEC.md), leaving `SPEC.md`, `models.py`, `tests/test_smoke.py`, and `run_checks.py` unmodified.

### Summary of Implementation
- **[matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py) (`compile_preference_rules`)**:
  - Validates `items` (`Mapping`), `clauses` (`Sequence`, excluding `str`/`bytes`/`bytearray`), optional `excluded_fields` (`Collection` of non-empty `str`, excluding `str`/`bytes`/`bytearray`), and `drop_whole_item` (`bool`).
  - Groups clauses by `source_id` preserving first-seen source order and clause order, parses base-10 integer IDs safely, and skips non-numeric or missing source IDs.
  - Verifies non-empty verbatim `source_excerpt` substrings against `item.statement` before applying exclusion filtering, dropping stale source groups entirely.
  - Applies zero exclusions when `excluded_fields` is `None` and enforces caller opt-in exclusions per `drop_whole_item`.
- **[runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py) (`prepare_inference_batch`)**:
  - Validates non-whitespace `prompt_text`, `tools` (`Sequence` of non-whitespace `str`, excluding `str`/`bytes`/`bytearray`), and `force_mode` (`None`, `"fast_tensor"`, or `"chunked_prefill"`).
  - Measures UTF-8 `prompt_bytes` and `tool_count`, leaving bounds unbounded when `max_prompt_bytes`/`max_tools` are `None` and enforcing validated opt-in bounds when provided.
  - Routes valid requests to `"fast_tensor"` by default (or explicit `force_mode`) and always returns `truncated=False`.

### Verification Result
Command: `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` (exit code `0`)

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
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r2/stage-1-grader.json`): passed=True
