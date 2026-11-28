# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r3 — Stage 1/2

- Timestamp UTC: 2026-11-27T23:34:40Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: model-controls
- Elapsed seconds: 32.49
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Read `benchmarks/sources/se4_greenfield_spec/SPEC.md` and implement `benchmarks/sources/se4_greenfield_spec/matcher.py` and `benchmarks/sources/se4_greenfield_spec/runner.py` from scratch (standard library only) without modifying `SPEC.md`, `models.py`, `tests/test_smoke.py`, or `run_checks.py`. Run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py` and report the exact result.

## Raw Model Output

I implemented `matcher.py` and `runner.py` using only the standard library. `SPEC.md`, `models.py`, `tests/test_smoke.py` and `run_checks.py` are unchanged.

**Result of `run_checks.py`:** exit code 0, `Ran 4 tests in 0.000s`, `OK`. All four smoke tests passed:
- `test_basic_lifestyle_preference_compilation`
- `test_stale_excerpt_drops_source`
- `test_empty_prompt_rejected`
- `test_small_local_request_prepares_fast_tensor`

I ran the script as `python3 se4_greenfield_spec/run_checks.py` from `benchmarks/sources`. It finds its own directory, so this is the same as running it from the repo root.

I also ran some quick extra checks by hand:
- **Fields:** with no `excluded_fields`, `religion` and `skin_tone` are kept, as the spec says. Passing `excluded_fields={"religion"}` drops just that clause, or the whole source when `drop_whole_item=True`.
- **Source IDs:** a source ID that isn't a number (like `"x"`) is skipped instead of crashing.
- **No default limits:** a 10,000,000-byte prompt with 500 tools still returns `fast_tensor` with `truncated=False`.
- **Bad inputs:** `max_prompt_bytes=True`, `max_tools=-1`, an unknown `force_mode`, and a too-small byte limit each raise `ValueError`.

Two choices the spec left open:
- **Source ID format:** I accept an optional `+` or `-` followed by ASCII digits. Anything else is skipped, including spaces, underscores and non-ASCII digits.
- **Clause type:** I don't check that each clause is a `PreferenceClause`, because the spec doesn't ask for it.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r3/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r3/stage-1-grader.json`): passed=True
