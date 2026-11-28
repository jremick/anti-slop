# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r3 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:36:07Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 42.30
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I wrote both modules using only the standard library, and `run_checks.py` passes all 4 smoke tests. I didn't modify `SPEC.md`, `models.py`, `tests/test_smoke.py` or `run_checks.py`.

**Exact result of `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`:**
```
test_basic_lifestyle_preference_compilation (test_smoke.SmokeMatcherTests) ... ok
test_stale_excerpt_drops_source (test_smoke.SmokeMatcherTests) ... ok
test_empty_prompt_rejected (test_smoke.SmokeRunnerTests) ... ok
test_small_local_request_prepares_fast_tensor (test_smoke.SmokeRunnerTests) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.000s

OK
```
Exit code: 0.

**`matcher.py`** follows the spec's rules in order:
- Clauses are grouped by `source_id`, keeping the order they first appear in.
- A `source_id` that isn't a whole number in base 10 is skipped rather than causing a crash.
- The excerpt check runs before any field exclusions. If one clause's excerpt doesn't appear word for word in the statement, the whole source is dropped.
- By default no fields are excluded. Exclusions only apply when the caller passes `excluded_fields`, and `drop_whole_item` decides whether a match drops one clause or the whole source.

**`runner.py`:**
- No limits apply unless the caller sets them: `max_prompt_bytes` must be a positive int and `max_tools` a non-negative int, and `True`/`False` are rejected for both.
- Requests go to `fast_tensor` unless `force_mode` says otherwise.
- `truncated` is always `False`.

The smoke tests don't cover most of the spec, so I also ran a separate check script. It confirmed:
- An excluded field drops just that clause by default, or the whole source with `drop_whole_item=True`.
- An empty excerpt drops its source.
- A source ID like `"abc"`, or one not in `items`, is skipped.
- Invalid `excluded_fields`, `drop_whole_item`, `max_prompt_bytes`, `max_tools` and `force_mode` values raise `ValueError`.
- The byte limit counts UTF-8 bytes (`"é"` is 2 bytes).
- A 5 MB prompt with 500 tools goes through unchanged on `fast_tensor`.

That script isn't saved as a test file.

**Decisions where the spec is open:**
- **Source ID format:** the spec only says "base-10 integer string," so I accept only plain ASCII digits with an optional `+` or `-` sign. Python's `int()` would also accept things like `" 12"` or `"1_000"`; these are skipped instead.
- **Exclusion fields:** `excluded_fields` is checked against `clause.field` exactly. The spec's list of supported fields isn't used to filter anything, since it doesn't ask for that.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r3/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r3/stage-1-grader.json`): passed=True
