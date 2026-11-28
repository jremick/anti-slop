# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r1 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:28:04Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 44.92
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I implemented both modules using only the standard library and left `SPEC.md`, `models.py`, `tests/test_smoke.py` and `run_checks.py` untouched. The check script passes.

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
Exit code: 0.

**What each module does**
- **`matcher.py`:** Clauses are grouped by `source_id`, keeping the order each source and clause first appeared.
  - An ID that isn't a plain base-10 integer string, like `"x"` or `"+1"`, is skipped instead of causing a crash. So is an ID with no matching item.
  - Every clause's excerpt is checked against the statement before any field exclusions apply. One failed excerpt skips the whole source, even if that clause would have been excluded anyway.
  - By default nothing is excluded, so fields like `religion` are compiled. Exclusions only apply when the caller passes `excluded_fields`, either dropping just the matching clauses or the whole source if `drop_whole_item=True`.
- **`runner.py`:** It validates all inputs and measures the prompt in UTF-8 bytes. There are no size or tool-count limits unless the caller sets them. The mode is always `fast_tensor` unless `force_mode` says otherwise, and `truncated` is always `False`.

**Extra checks:** The four smoke tests don't cover most of the spec, so I ran some edge cases by hand, and all behaved as the spec requires:
- each exclusion mode
- a failed excerpt on a clause that would have been excluded
- non-numeric and unknown source IDs
- a 6 MB prompt with 500 tools still running as `fast_tensor` without truncation
- `force_mode`
- limits that are exceeded, as well as limits set to booleans, zero or negative values
- bad tool lists

These were one-off checks, not tests added to the repo.

**Choices the spec didn't settle:**
- `clauses` containing something other than `PreferenceClause` raises `ValueError` instead of an `AttributeError`.
- Negative IDs like `"-3"` count as valid integers.
- Field names outside the listed schema are not filtered out, because the spec doesn't ask for that.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r1/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r1/stage-1-grader.json`): passed=True
