# pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:53:22Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 143.77
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

Implemented [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py) and [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py) using only the Python standard library per [SPEC.md](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/SPEC.md), without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`.

### Summary of Implementation
- [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py) (`compile_preference_rules`):
  - Validates `items` (`Mapping`), `clauses` (`Sequence`, excluding `str`/`bytes`/`bytearray`), optional `excluded_fields` (`Collection` of non-empty `str`, excluding `str`/`bytes`/`bytearray`), and `drop_whole_item` (`bool`), raising `ValueError` on invalid inputs.
  - Groups clauses by `source_id` preserving first-seen source order and clause order, parses base-10 integer IDs safely without crashing on non-numeric strings, and skips missing items.
  - Runs verbatim non-empty `source_excerpt` verification against `item.statement` across all clauses in a group before applying opt-in exclusions, skipping the entire source group if any clause fails.
  - Applies zero default field exclusions when `excluded_fields is None`, and honors caller-provided `excluded_fields` with both `drop_whole_item=True` and `drop_whole_item=False`.
- [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py) (`prepare_inference_batch`):
  - Validates non-whitespace `prompt_text`, `tools` sequence of non-whitespace strings, optional `force_mode` (`"fast_tensor"` or `"chunked_prefill"`), optional strictly positive `int` `max_prompt_bytes` (rejecting `bool`), and optional non-negative `int` `max_tools` (rejecting `bool`).
  - Measures UTF-8 `prompt_bytes` and `tool_count`, leaving both unbounded when limits are `None`, routing to `"fast_tensor"` by default (or `force_mode` when specified), and always returning `truncated=False`.

### Verification
Ran `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` (exit code `0`):

```text
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

Also ran standalone contract checks covering input validation, source ordering, stale-excerpt precedence over exclusions, `drop_whole_item` modes, multi-byte UTF-8 counting, boundary limits, and multi-megabyte / high-tool-count unbounded requests (all passed).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r2/stage-1-grader.json`): passed=True
