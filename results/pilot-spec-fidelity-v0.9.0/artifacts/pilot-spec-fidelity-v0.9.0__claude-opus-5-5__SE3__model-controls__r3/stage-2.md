# pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__model-controls__r3 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:26:42Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: model-controls
- Elapsed seconds: 12.17
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

## Fix SE3 spec-fidelity defects

- `matcher.py`: Removed hardcoded `PROTECTED_FIELDS` (`skin_tone`) ban; every user-declared field is honored when `excluded_fields` is `None`. Added caller opt-in `excluded_fields`: drops only excluded clauses (whole item only with `drop_whole_item=True`). Excerpt verification unchanged.
- `runner.py`: Removed 262KB prompt cap, 64-tool cap, and 8192-byte `single_token_fallback`; all accepted requests route on `fast_tensor`.

No hardcoded field exclusions or capacity caps remain. Supported opt-in bounds: `max_prompt_bytes` (positive int) and `max_tools` (non-negative int), both validated and enforced via `ValueError`.

Verification: `python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` → Ran 4 tests, OK (previously 2 failures, 1 error). Tests unchanged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__model-controls__r3/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__claude-opus-5-5__SE3__model-controls__r3/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 93/120 (raw=98)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
