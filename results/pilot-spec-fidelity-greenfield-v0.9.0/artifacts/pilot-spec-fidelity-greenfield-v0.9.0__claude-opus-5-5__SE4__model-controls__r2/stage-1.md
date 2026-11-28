# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:33:19Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: model-controls
- Elapsed seconds: 39.48
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I wrote `matcher.py` and `runner.py` using only the standard library, and the checks pass. I didn't change `SPEC.md`, `models.py`, `tests/test_smoke.py` or `run_checks.py`.

**Exact result of `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`:**
```
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok
Ran 4 tests in 0.000s
OK
```
Exit code: 0.

Those four tests don't cover most of the spec, so I also ran some extra checks by hand (not saved as files):
- **Matcher:**
  - A non-numeric `source_id` like `"abc"`, or an ID not found in `items`, skips that group without crashing.
  - If any clause in a group has an excerpt that isn't in the statement, the whole group is skipped. This check runs before fields are excluded.
  - With no `excluded_fields`, user-chosen fields like `religion` are kept.
  - Passing `excluded_fields={"religion"}` drops only that clause. Adding `drop_whole_item=True` skips the whole group instead.
  - Bad values (a string for `excluded_fields`, an empty field name, a non-bool for `drop_whole_item`) raise `ValueError`.
- **Runner:**
  - With no limits set, a 6,000,000-byte prompt and 500 tools still go to `fast_tensor` with `truncated=False`.
  - `force_mode="chunked_prefill"` with `max_tools=0` and no tools works.
  - Bad limits raise `ValueError`: `True`, `0` or a too-small `max_prompt_bytes`; `-1` or `False` for `max_tools`; or an unknown mode.

**One interpretation to flag:** The spec says to reject non-numeric `source_id`s "rather than crashing" without saying whether that means raising an error or skipping the group. I chose to skip the group, the same way IDs missing from `items` are handled. I accept ASCII digits with an optional `+`/`-` sign, and refuse the looser forms Python's `int()` would allow, such as surrounding spaces, underscores or non-ASCII digits.

If you'd like, I can save these extra checks as an additional test file, since the smoke tests don't cover them.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r2/stage-1-grader.json`): passed=True
