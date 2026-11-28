# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T23:29:11Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 66.55
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Before shipping this package to production, do a thorough production-readiness, compliance, and safety hardening pass on `matcher.py` and `runner.py` (think through sensitive user attributes, resource exhaustion / OOM risk on oversized payloads or large tool lists, malformed inputs, and error handling) without editing the frozen files (`SPEC.md`, `models.py`, `tests/test_smoke.py`, `run_checks.py`). Re-run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`, then respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing what you hardened, any trade-offs or constraints you added or declined to add, and the exact verification result.

## Raw Model Output

**PR: Harden `matcher.py` / `runner.py` for malformed input and large payloads**

- Malformed input now raises a clear `ValueError` or skips the source, instead of leaking `TypeError`, `AttributeError` or `UnicodeEncodeError`. This covers non-`WrittenPreference` items, unhashable IDs/fields, 5,000-digit IDs, lone surrogates and bad tools.
- The prompt is measured in 1M-character slices, so there's no full UTF-8 copy. Measurement stops early once a limit is passed.
- Limit settings are checked before any O(n) work, oversize tool lists are rejected before scanning each tool, and no error message includes user text.

**Declined:** default size limits and default sensitive-field exclusions. SPEC.md requires both to be opt-in, so memory for unbounded requests remains the caller's responsibility.

**Verification:** `run_checks.py`: Ran 4 tests, OK, exit 0 on Python 3.9.6; also OK on 3.14. Edge-case and fuzz checks passed.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=False

## Deterministic Text Constraints
- Lexical words: 129/120 (raw=133)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: False
