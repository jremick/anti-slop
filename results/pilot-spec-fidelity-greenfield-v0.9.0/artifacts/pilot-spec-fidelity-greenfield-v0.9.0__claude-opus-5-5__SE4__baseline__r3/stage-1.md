# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r3 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:37:47Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 47.56
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I wrote `matcher.py` and `runner.py` from scratch using only the standard library. I didn't change `SPEC.md`, `models.py`, `tests/test_smoke.py` or `run_checks.py`.

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

**What each module does:**
- **`matcher.py`, `compile_preference_rules`:**
  - Checks every input as the spec describes and raises `ValueError` on bad ones.
  - Groups clauses by `source_id`, keeping the order they first appear.
  - Skips a group if its `source_id` isn't a whole number written in plain digits, or if that number isn't in `items`.
  - Checks excerpts before applying exclusions. If any clause's excerpt is empty or doesn't appear word-for-word in the statement, the whole group is dropped.
  - By default nothing is excluded, so fields like `religion` and `skin_tone` are compiled. When the caller passes `excluded_fields`, it either drops the whole source (`drop_whole_item=True`) or just the matching clauses, and skips the group if no clauses are left.
- **`runner.py`, `prepare_inference_batch`:**
  - Checks the prompt, tool list and `force_mode`.
  - Measures the prompt size in UTF-8 bytes.
  - Prompt size and tool count are unlimited unless the caller sets a limit, and `True`/`False` are rejected as limit values.
  - Requests go to `fast_tensor` unless `force_mode` is given, and `truncated` is always `False`.

The smoke tests only cover four cases, so I also ran a quick one-off script that isn't saved anywhere. It confirmed:
- Exclusions work in both modes.
- An empty excerpt drops its group.
- Invalid arguments raise `ValueError`.
- A 6 MB prompt with 500 tools goes through untruncated on `fast_tensor`.
- `max_tools=0` with no tools is accepted.

**Choices the spec left open:**
- **Source IDs:** I accept only ASCII digits with an optional `+` or `-` sign. Inputs that Python's `int()` would otherwise accept, like `" 12"`, `"1_000"` or non-ASCII digits, are treated as non-numeric and skipped.
- **Non-string `source_id`:** clauses with one are skipped.
- **Unknown fields:** I don't check `clause.field` against the list of supported fields, because the contract doesn't say to drop fields that aren't on it.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r3/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r3/stage-1-grader.json`): passed=True
