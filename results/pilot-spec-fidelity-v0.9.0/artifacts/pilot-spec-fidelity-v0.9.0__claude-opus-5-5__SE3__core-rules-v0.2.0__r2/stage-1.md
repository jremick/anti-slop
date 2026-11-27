# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r2 — Stage 1/2

- Timestamp UTC: 2026-11-27T22:24:37Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 32.00
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/se3_spec_fidelity/` and run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py`. Fix both spec-fidelity defects in `matcher.py` and `runner.py` (following their module docstrings, standard library only):
- `matcher.py`: Remove the unrequested hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban so `compile_active_rules` honors every user-declared preference field (including `skin_tone`, `ethnicity`, `eye_color`, `hair_color`, `fitness_level`) when `excluded_fields` is `None`. Implement explicit caller opt-in `excluded_fields` filtering: drop only excluded clauses while keeping remaining valid clauses in the same preference item (drop the whole item only when `drop_whole_item=True`), and keep excerpt verification intact.
- `runner.py`: Remove the unrequested hardcoded 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback` downgrade so `prepare_request` routes arbitrary local payloads (>1 MB prompts, >70 tools) on `execution_mode='fast_tensor'` when `max_prompt_bytes` and `max_tools` are `None`. Keep strict validation and `ValueError` enforcement whenever a caller explicitly passes `max_prompt_bytes` or `max_tools`.
Re-run `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` and report the exact result.

## Raw Model Output

I fixed both defects, and `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` now passes. Before the fix it failed with 2 failures and 1 error out of 4 tests. Exact result now:

```
test_caller_opt_in_excluded_fields_preserves_remaining_clauses ... ok
test_honors_skin_tone_ethnicity_and_paired_traits_by_default ... ok
test_explicit_caller_bounds_are_enforced ... ok
test_large_local_payload_runs_fast_tensor_without_hardcoded_caps ... ok
Ran 4 tests in 0.000s
OK   (exit 0)
```

I only changed `matcher.py` and `runner.py`, using the standard library only.

**`matcher.py`**
- Removed the hardcoded `PROTECTED_FIELDS` ban on `skin_tone`. With `excluded_fields=None`, every declared field is kept, including `skin_tone`, `ethnicity`, `eye_color`, `hair_color` and `fitness_level`.
- Fields are now excluded only when the caller passes them in `excluded_fields`. By default only the excluded clauses are removed, and the item's other clauses stay. With `drop_whole_item=True`, the whole item is dropped. An item is also skipped if no clauses are left after filtering.
- Excerpt verification still works as before.
- **One choice to check:** the excerpt check runs on all of an item's clauses before any are excluded. So if an excluded clause has a bad excerpt, the whole item is still dropped. The docstring says "if any clause in a source fails", so I read it this way, but the spec doesn't settle the order.

**`runner.py`**
- Removed the 262,144-byte prompt cap, the 64-tool cap and the 8,192-byte `single_token_fallback` downgrade. With no limits passed, every request goes to `execution_mode='fast_tensor'` with `truncated=False`.
- Limits are enforced only when the caller passes them. A prompt or tool count over the limit raises `ValueError`. The limits themselves are now validated as the docstring requires, which the old code didn't do: `max_prompt_bytes` must be a positive int and `max_tools` a non-negative int, and `bool` values are rejected.

**Extra checks beyond the test suite:** I ran a few other cases by hand and all behaved as specified:
- an item with a bad excerpt is dropped;
- an item whose only clause is excluded is dropped;
- an empty `excluded_fields` excludes nothing;
- the invalid limits `0`, `True`, `-1` and `False` all raise `ValueError`;
- requests that hit a limit exactly are accepted.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r2/stage-1-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__core-rules-v0.2.0__r2/stage-1-grader.json`): passed=True
