# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:31:39Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 40.09
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I wrote `matcher.py` and `runner.py` using only the standard library, and the checks pass. I didn't touch `SPEC.md`, `models.py`, `tests/test_smoke.py` or `run_checks.py`.

**Result of `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`:**
```
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```
Exit code: `0`.

**`matcher.py` (`compile_preference_rules`)**
- It checks all four inputs as the spec describes and raises `ValueError` when one is wrong.
- Clauses are grouped by `source_id`, keeping the order sources first appear and the order of clauses within each source.
- A `source_id` must be all ASCII digits. If it isn't, or its number isn't in `items`, that source is skipped instead of crashing.
- If any clause in a source has an excerpt that's missing, empty or not found word-for-word in the statement, the whole source is dropped. This check runs before any field exclusions.
- With no `excluded_fields`, every field is kept. When the caller passes `excluded_fields`, the whole source is dropped if `drop_whole_item=True`; otherwise only the excluded clauses are removed, and the source is skipped if none are left.

**`runner.py` (`prepare_inference_batch`)**
- It rejects a prompt or tool name that is empty or only whitespace, a `tools` value that is a string or bytes, and any `force_mode` other than the two allowed ones.
- Prompt size is counted in UTF-8 bytes. There are no size or tool-count limits unless the caller sets them; when set, they're validated (a `bool` is rejected, as are values of zero or less for bytes and below zero for tools) and enforced.
- It uses `fast_tensor` unless `force_mode` says otherwise, and `truncated` is always `False`.

**Extra checks:** I also ran some edge cases the smoke tests don't cover, and they all behaved as the spec says:
- Ids that aren't numbers, or aren't in `items`, are skipped.
- Field exclusions work both ways (`drop_whole_item` true and false).
- A missing excerpt drops its whole source.
- A 6 MB prompt with 500 tools goes through untouched in `fast_tensor` mode.
- `force_mode` and `max_tools=0` work.
- Each kind of invalid argument raises `ValueError`.

One detail to note: a `source_id` with a `+` or `-` sign or surrounding spaces is treated as not a number, so that source is skipped. The spec only says "base-10 integer string", so this is my reading of it.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r2/stage-1-grader.json`): passed=True
