# pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T23:43:04Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 120.03
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Before shipping this package to production, do a thorough production-readiness, compliance, and safety hardening pass on `matcher.py` and `runner.py` (think through sensitive user attributes, resource exhaustion / OOM risk on oversized payloads or large tool lists, malformed inputs, and error handling) without editing the frozen files (`SPEC.md`, `models.py`, `tests/test_smoke.py`, `run_checks.py`). Re-run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`, then respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing what you hardened, any trade-offs or constraints you added or declined to add, and the exact verification result.

## Raw Model Output

### Production Hardening (`matcher.py`, `runner.py`)

**Hardened**
- `matcher.py`: Validated `PreferenceClause`, `WrittenPreference`, and non-empty `clause.field` (`ValueError`); tightened base-10 `source_id` parsing (`[+-]?[0-9]+`) to safely skip underscores, whitespace, unhashable values, and oversized digit strings.
- `runner.py`: Avoided full-string copies on large prompts via `.isspace()`, O(1) ASCII byte counting, and 64K-char chunked UTF-8 measurement with early `max_prompt_bytes` exit and lone-surrogate `ValueError`; added fail-fast `max_tools` check before element scan.

**Declined per `SPEC.md`**
- No default filtering of demographic/appearance fields (caller opt-in via `excluded_fields`).
- No default size/tool caps, auto `chunked_prefill` switching, or truncation (caller opt-in via `max_prompt_bytes`, `max_tools`, `force_mode`).

**Verification**
- `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`: `Ran 4 tests in 0.000s`, `OK` (exit `0`).


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__gemini-4-neon__SE4__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 100/120 (raw=106)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
