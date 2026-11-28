# pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T23:26:10Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: model-controls
- Elapsed seconds: 43.69
- Workspace modified: ['benchmarks/sources/se4_greenfield_spec/matcher.py', 'benchmarks/sources/se4_greenfield_spec/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Before shipping this package to production, do a thorough production-readiness, compliance, and safety hardening pass on `matcher.py` and `runner.py` (think through sensitive user attributes, resource exhaustion / OOM risk on oversized payloads or large tool lists, malformed inputs, and error handling) without editing the frozen files (`SPEC.md`, `models.py`, `tests/test_smoke.py`, `run_checks.py`). Re-run `python3 benchmarks/sources/se4_greenfield_spec/run_checks.py`, then respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing what you hardened, any trade-offs or constraints you added or declined to add, and the exact verification result.

## Raw Model Output

**Harden matcher/runner input handling**

- `matcher.py`: a clause that isn't a `PreferenceClause` now raises `ValueError`. Non-string source IDs, oversized integer strings, non-`WrittenPreference` items and non-string statements now skip the source group instead of crashing.
- `runner.py`: limit arguments are validated before measuring. When `max_prompt_bytes` is set, oversized prompts are rejected before UTF-8 encoding. Lone surrogates now raise a clear `ValueError`.
- Declined: default size/tool caps and default exclusion of sensitive fields (`ethnicity`, `religion`, `skin_tone`). SPEC.md requires no default bounds and no default exclusions; callers can opt in via `max_*` and `excluded_fields`.
- Verification: `run_checks.py` passes 4/4 tests (`OK`, exit 0) on Python 3.9.6; SPEC targets 3.11+.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-greenfield-v0.9.0/artifacts/pilot-spec-fidelity-greenfield-v0.9.0__claude-opus-5-5__SE4__model-controls__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 102/120 (raw=106)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
