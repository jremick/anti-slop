# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__model-controls__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:22:51Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: model-controls
- Elapsed seconds: 13.09
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

## Spec-fidelity fixes (SE3)

**matcher.py:** Removed the hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban. `compile_active_rules` now honors every user-declared field when `excluded_fields` is `None`. Caller opt-in `excluded_fields` drops only matching clauses, keeping remaining valid clauses; `drop_whole_item=True` drops the whole item. Excerpt verification is unchanged.

**runner.py:** Removed the 262,144-byte prompt cap, 64-tool cap, and 8,192-byte `single_token_fallback` downgrade; unbounded requests route on `fast_tensor`.

**Remaining limits:** No hardcoded field exclusions or capacity caps remain. Supported opt-in bounds: `max_prompt_bytes` (positive int) and `max_tools` (non-negative int), validated and enforced with `ValueError`.

**Verification:** `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` → `Ran 4 tests`, `OK` (exit 0); tests unmodified.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__model-controls__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__model-controls__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 97/120 (raw=100)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
