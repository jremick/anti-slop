# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:25:26Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: model-controls
- Elapsed seconds: 34.06
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I implemented `matcher.py` and `runner.py` using only the standard library, and the check script passes. I didn't change `SPEC.md`, `models.py`, `tests/test_smoke.py` or `run_checks.py`.

**Exact result of `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`:**
```
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok
----------------------------------------------------------------------
Ran 4 tests in 0.001s

OK
```
Exit code: 0.

The four smoke tests only cover the basic cases, so I also ran a one-off script for cases they don't reach. Everything behaved as the spec says:
- **No exclusions by default:** with no `excluded_fields`, user-chosen fields like `religion` are compiled.
- **Exclusions when asked:** listing a field in `excluded_fields` drops only that clause; with `drop_whole_item=True`, the whole source is skipped instead.
- **Bad source IDs:** a non-numeric `source_id` is skipped rather than crashing.
- **No size limits by default:** a 6 MB prompt with 500 tools goes through on `fast_tensor` and is not truncated.
- **Forced mode:** `force_mode="chunked_prefill"` is used when given.
- **Rejected inputs:** a `bool` or `0` byte limit, a negative `max_tools`, an unknown mode, and a prompt over its byte limit all raise `ValueError`.

**One decision of mine:** the spec only says "base-10 integer string", so I read that strictly. Only ASCII digits with an optional leading `-` count; anything else, like `" 1"`, `"+1"` or `"1_0"`, is treated as non-numeric and its group is skipped.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r1/stage-1-grader.json`): passed=True
