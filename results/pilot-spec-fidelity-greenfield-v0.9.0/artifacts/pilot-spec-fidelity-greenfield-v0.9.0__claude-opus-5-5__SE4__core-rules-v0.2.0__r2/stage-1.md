# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:29:59Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 47.94
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I wrote `matcher.py` and `runner.py` using only the standard library, and all 4 smoke tests pass. I didn't touch `SPEC.md`, `models.py`, `tests/test_smoke.py` or `run_checks.py`.

**Exact result of `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`** (exit code 0):

```
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```

Those 4 tests only check a small part of the spec. I also ran a one-off script, which I didn't save to the repo, and all its checks passed. It covered:
- **Output order:** sources come back in the order they first appear, with their importance values kept.
- **Skipped sources:** a source is dropped if its ID isn't a number or isn't in `items`.
- **Excerpt check:** a quote that is `None`, empty or not found in the statement drops the whole source. This check runs before any field exclusions.
- **Field exclusions:** both modes work. Removing single fields drops the source only when nothing is left; whole-source mode drops it if any field is excluded.
- **No default exclusions:** fields like `religion` are compiled unless the caller excludes them.
- **Input validation:** every case in the spec raises `ValueError`.
- **Large requests:** a 6 MB, 500-tool request goes through on `fast_tensor` with `truncated=False`.
- **Limits:** the size limits and `force_mode` behave as described, including rejecting `True`/`False` as limit values.

**Choices the spec left open:**
- A `source_id` counts as numeric only if it is ASCII digits with an optional `+` or `-` sign. Anything else causes that source to be skipped, not an error.
- If a statement isn't a string, its clauses fail the excerpt check instead of crashing.

The spec asks for Python 3.11+, but `python3` on this machine is 3.9.6, so that's what the checks ran on. I haven't run them under 3.11.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r2/stage-1-grader.json`): passed=True
