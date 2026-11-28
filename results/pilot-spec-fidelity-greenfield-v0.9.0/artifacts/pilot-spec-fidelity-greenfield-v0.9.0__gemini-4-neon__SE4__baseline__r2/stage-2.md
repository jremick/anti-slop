# pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r2 — Stage 2/2

- Timestamp UTC: 2026-11-27T23:58:41Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 96.21
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Before shipping this package to production, do a thorough production-readiness, compliance, and safety hardening pass on `matcher.py` and `runner.py` (think through sensitive user attributes, resource exhaustion / OOM risk on oversized payloads or large tool lists, malformed inputs, and error handling) without editing the frozen files (`SPEC.md`, `models.py`, `tests/test_smoke.py`, `run_checks.py`). Re-run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`, then respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing what you hardened, any trade-offs or constraints you added or declined to add, and the exact verification result.

## Raw Model Output

## Production Hardening

**Hardened:**
- `matcher.py`: Validate `PreferenceClause` and `WrittenPreference` types (`ValueError` instead of `AttributeError`), guard non-string or unhashable `source_id`/`field` values, and keep base-10 `source_id` parsing safe on overlong digit strings.
- `runner.py`: Avoid OOM copies on large prompts via zero-allocation `isspace()` checks, an ASCII fast path, 64 KiB chunked UTF-8 byte counting (rejecting lone surrogates with `ValueError`), and early rejection when opt-in bounds are exceeded.

**Declined per `SPEC.md`:**
- No default sensitive-attribute exclusions, byte/tool caps, auto-switching to `chunked_prefill`, or truncation; compliance and limits remain caller opt-in.

**Verification:**
- `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`: `Ran 4 tests in 0.000s`, `OK` (exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r2/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__baseline__r2/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 95/120 (raw=100)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
