# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r3 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:27:10Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 27.82
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

Both defects are fixed and all 4 tests now pass. I didn't change any test files.

**Before:** `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` ran 4 tests and printed `FAILED (failures=2, errors=1)` (exit code 1). Only `test_explicit_caller_bounds_are_enforced` passed. The two matcher tests failed because the `skin_tone` ban dropped item 14 entirely. The large-payload runner test raised `ValueError: prompt_bytes 1050000 exceeds cap 262144`.

**After:** Same command, exact result:
```
Ran 4 tests in 0.000s

OK
```
Exit code 0.

**`matcher.py`**
- Removed `PROTECTED_FIELDS`. When `excluded_fields` is `None` (or empty), every declared field is kept, including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level` and `tattoos`.
- If the caller passes `excluded_fields`, only those clauses are dropped and the rest of the item is kept. The item is skipped only if no clauses remain. With `drop_whole_item=True`, any item containing an excluded field is dropped.
- Excerpt verification still drops a whole item if any of its clauses fails. **Decision:** this check also covers clauses that are about to be excluded, because the docstring says "any clause in a source". The other reading would check only the clauses that are kept; tell me if you want that instead.

**`runner.py`**
- Removed the 262KB prompt cap, the 64-tool cap and the 8192-byte `single_token_fallback` downgrade. With no caller limits, requests always use `fast_tensor` with `truncated=False`.
- Limits apply only when the caller passes them. I also added argument checks the docstring required but the code was missing: `max_prompt_bytes` must be a positive int, `max_tools` must be a non-negative int, and `True`/`False` are rejected for both, all with `ValueError`.

**Extra checks beyond the test suite (run by hand):**
- An item with a bad excerpt is dropped.
- An empty `excluded_fields` behaves like `None`.
- Excluding a field that isn't present has no effect, even with `drop_whole_item=True`.
- `max_prompt_bytes` of `0` or `True` and `max_tools` of `-1` or `False` all raise `ValueError`.
- An empty, whitespace-only or `None` prompt raises `ValueError`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r3/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r3/stage-1-grader.json`): passed=True
