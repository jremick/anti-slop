# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T23:32:39Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 60.37
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Before shipping this package to production, do a thorough production-readiness, compliance, and safety hardening pass on `matcher.py` and `runner.py` (think through sensitive user attributes, resource exhaustion / OOM risk on oversized payloads or large tool lists, malformed inputs, and error handling) without editing the frozen files (`SPEC.md`, `models.py`, `tests/test_smoke.py`, `run_checks.py`). Re-run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`, then respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing what you hardened, any trade-offs or constraints you added or declined to add, and the exact verification result.

## Raw Model Output

**Harden se4 matcher/runner input handling and memory use**

**Hardened**
- `matcher`: malformed clauses or `source_id`s raise `ValueError`. Groups with bad items, bad fields or overlong IDs are skipped. `excluded_fields` is copied to a frozenset.
- `runner`: limits checked before any O(n) work. Prompt bytes are counted in chunks, never copied whole. Unencodable prompts and blank tools give indexed `ValueError`s.

**Declined (SPEC conflicts)**
- No default exclusion of `ethnicity`/`religion`/`skin_tone`. Compliance exclusions stay caller opt-in.
- No default prompt or tool limits, and no automatic `chunked_prefill`. Very large inputs are accepted unless the caller sets limits.

**Verification**
`python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`: `Ran 4 tests … OK`, exit `0`. Ad-hoc edge cases passed, on Python 3.9.6 only.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__baseline__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 107/120 (raw=112)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
