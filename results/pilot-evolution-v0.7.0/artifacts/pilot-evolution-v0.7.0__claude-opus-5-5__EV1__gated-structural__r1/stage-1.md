# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1 — Stage 1/4

- Timestamp UTC: 2026-11-27T01:29:14Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 85.35
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_upgrades.py']
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/ev1_order_ledger/` and run `python3 benchmarks/sources/ev1_order_ledger/run_checks.py`. Implement Turn 1 (mid-cycle prorated plan upgrades + idempotency, stdlib only):
- Add `OrderService.upgrade_subscription(subscription_id, new_plan_id, days_remaining, cycle_days, *, idempotency_key)` backed by canonical helpers in `pricing.py` and `ledger.py`.
- Compute exact integer-cent half-up proration `round_half_up_div((new_plan.monthly_cents - old_plan.monthly_cents) * days_remaining, cycle_days)` and tax via `pricing.compute_tax_cents(taxable_cents, new_plan.tax_bps)`, update `subscription.plan_id`, and record a `LedgerEntry` with `kind='plan_upgrade'` and `reference_id=subscription_id`.
- Reject unknown IDs, non-upgrades (`new_plan.monthly_cents <= old_plan.monthly_cents`), invalid bounds (`cycle_days <= 0`, `days_remaining < 0`, `days_remaining > cycle_days`), booleans, or empty `idempotency_key` with `ValidationError`.
- Enforce idempotency: replaying the same `idempotency_key` with identical arguments returns the original `LedgerEntry` without adding a duplicate entry; reusing `idempotency_key` with different arguments raises `ValidationError`.
- Add strong unit tests in `benchmarks/sources/ev1_order_ledger/tests/` covering proration half-up rounding, error bounds, and idempotency replay/conflict, and verify `run_checks.py` exits 0.

## Raw Model Output

Turn 1 is in: `OrderService.upgrade_subscription(...)` now charges prorated plan upgrades and handles repeated requests safely. `run_checks.py` passes 22 tests (the 4 existing ones plus 18 new) and exits 0. Everything is standard library only.

**Where the code went**
- **`pricing.py`**: two new helpers. `validate_upgrade_window` checks the day counts. `compute_upgrade_proration_cents` rejects anything that isn't a real price increase and computes `round_half_up_div((new - old) * days_remaining, cycle_days)`.
- **`ledger.py`**: a store for idempotency keys. `find_idempotent_entry` returns the original entry on a matching replay and raises `ValidationError` if the key was used with different arguments. `record_idempotent_entry` saves the entry and the key together.
- **`api.py`**: `upgrade_subscription` checks the inputs, computes the charge, calculates tax with `compute_tax_cents(subtotal, new_plan.tax_bps)`, and records a `plan_upgrade` entry with `reference_id=subscription_id`. It then switches the subscription to the new plan. The entry's metadata records the old and new plan IDs, the day counts and the key.

**Behaviour you might not assume**
- **Replays are checked before the plan comparison.** After the first upgrade, the subscription is already on the new plan, so the "must be an upgrade" check would fail if it ran on a replay. Running the replay check first means a retry gets the original entry back instead of an error.
- **Bad input is rejected before the replay check.** Wrong types, booleans and out-of-range day counts are caught first. Without this, Python treats `True == 1`, so replaying `days_remaining=1` as `True` would wrongly count as a match.
- **Failed calls change nothing.** A rejected call adds no entry, leaves the plan alone and doesn't use up its key, so you can retry with the same key.
- **`days_remaining=0` is allowed.** It records a 0-cent entry and still switches the plan, because the spec only rejects negative values. Say if you'd rather reject it.
- **Keys are shared across operations.** The stored request details include the operation name, so a future operation can share the same key store without clashing.

**Tests** (`tests/test_upgrades.py`)
- **Rounding:** exact halves round up (0.5→1, 1.5→2, 2.5→3, not banker's rounding), plus cases just below and just above half.
- **Exhaustive check:** every combination of several price differences, cycle lengths and day counts is compared against an exact fraction-based calculation.
- **Tax:** a case where tax rounds up from exactly 82.5→83, and a case confirming the new plan's tax rate is used.
- **Upgrades in a row:** a second upgrade is prorated from the plan the subscription is currently on.
- **Rejections:** unknown IDs, same-price and cheaper plans, every day-count limit, booleans, floats, and empty or non-string keys. Each case confirms nothing was changed.
- **Idempotency:** a replay returns the same entry object without a duplicate charge. Reusing a key with a different value in any argument raises `ValidationError`. `True` is not accepted as a replay of `1`, and a failed call doesn't reserve its key.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-1-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-1-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-1-grader.json`): passed=False
