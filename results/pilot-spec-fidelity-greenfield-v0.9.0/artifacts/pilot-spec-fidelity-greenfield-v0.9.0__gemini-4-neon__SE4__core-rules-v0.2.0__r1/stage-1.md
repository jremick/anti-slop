# pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:41:04Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 152.68
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

Implemented [matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py) and [runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py) using only the Python standard library per [SPEC.md](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/SPEC.md), leaving `SPEC.md`, `models.py`, `tests/test_smoke.py`, and `run_checks.py` unmodified.

### Summary of Implementation
- **`compile_preference_rules` ([matcher.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/matcher.py))**:
  - Validates `items` (`Mapping`), `clauses` (`Sequence`, excluding `str`/`bytes`/`bytearray`), `excluded_fields` (`None` or `Collection` of non-empty `str`, excluding `str`/`bytes`/`bytearray`), and `drop_whole_item` (`bool`), raising `ValueError` otherwise.
  - Groups clauses by `source_id` preserving first-seen source and clause order, safely parses base-10 integer `source_id`s and skips invalid/missing IDs.
  - Runs verbatim non-empty `source_excerpt` verification against `item.statement` before exclusion filtering, skipping the whole source group on any failure.
  - Applies zero exclusions when `excluded_fields is None` and supports opt-in clause-level (`drop_whole_item=False`) or whole-group (`drop_whole_item=True`) exclusions, returning `CompiledRules` with `RuleSource` tuples.
- **`prepare_inference_batch` ([runner.py](file://<TMP_WORKSPACE>/benchmarks/sources/se4_greenfield_spec/runner.py))**:
  - Validates `prompt_text`, `tools` (and each element), `force_mode`, and opt-in `max_prompt_bytes` (`> 0`, non-`bool` `int`) and `max_tools` (`>= 0`, non-`bool` `int`), raising `ValueError` on invalid inputs or exceeded bounds.
  - Measures UTF-8 `prompt_bytes` and `tool_count` without imposing default bounds, routes on `"fast_tensor"` unless `force_mode` is set, and always returns `truncated=False`.

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

Also ran an additional 14-test scratch verification suite ([verify_spec.py](file://<HOME>/.gemini/antigravity-cli/brain/3514f470-edac-40c0-847d-b292a94219ac/scratch/verify_spec.py)) covering all input validation rules, schema fields, excerpt-before-exclusion ordering, `drop_whole_item` modes, multi-MB prompts/large tool lists, UTF-8 byte bounds, and `force_mode` routing (`Ran 14 tests in 0.001s — OK`).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r1/stage-1-grader.json`): passed=True
