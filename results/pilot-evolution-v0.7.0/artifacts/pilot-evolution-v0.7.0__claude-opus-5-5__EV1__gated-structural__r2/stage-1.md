# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2 — Stage 1/4

- Timestamp UTC: 2026-11-27T01:48:49Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 93.21
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_subscription_upgrade.py']
- Workspace deleted: []

## Prompt

Inspect `benchmarks/sources/ev1_order_ledger/` and run `python3 benchmarks/sources/ev1_order_ledger/run_checks.py`. Implement Turn 1 (mid-cycle prorated plan upgrades + idempotency, stdlib only):
- Add `OrderService.upgrade_subscription(subscription_id, new_plan_id, days_remaining, cycle_days, *, idempotency_key)` backed by canonical helpers in `pricing.py` and `ledger.py`.
- Compute exact integer-cent half-up proration `round_half_up_div((new_plan.monthly_cents - old_plan.monthly_cents) * days_remaining, cycle_days)` and tax via `pricing.compute_tax_cents(taxable_cents, new_plan.tax_bps)`, update `subscription.plan_id`, and record a `LedgerEntry` with `kind='plan_upgrade'` and `reference_id=subscription_id`.
- Reject unknown IDs, non-upgrades (`new_plan.monthly_cents <= old_plan.monthly_cents`), invalid bounds (`cycle_days <= 0`, `days_remaining < 0`, `days_remaining > cycle_days`), booleans, or empty `idempotency_key` with `ValidationError`.
- Enforce idempotency: replaying the same `idempotency_key` with identical arguments returns the original `LedgerEntry` without adding a duplicate entry; reusing `idempotency_key` with different arguments raises `ValidationError`.
- Add strong unit tests in `benchmarks/sources/ev1_order_ledger/tests/` covering proration half-up rounding, error bounds, and idempotency replay/conflict, and verify `run_checks.py` exits 0.

## Raw Model Output

Turn 1 is done: `OrderService.upgrade_subscription` now charges prorated, taxed upgrades and handles idempotency. `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` exits 0, with all 19 tests passing (the 4 original ones plus 15 new). Everything uses only the standard library.

**Pricing (`pricing.py`).** A new `compute_upgrade_proration(old_plan, new_plan, days_remaining, cycle_days)` returns `(subtotal, tax, total)`. It rejects bad bounds, booleans and non-upgrades with `ValidationError`, then computes `round_half_up_div(delta * days_remaining, cycle_days)` and taxes it with `compute_tax_cents(subtotal, new_plan.tax_bps)`.

**Ledger (`ledger.py`).** It now keeps a store of idempotency keys, each mapped to a fingerprint of the original arguments and the ledger entry ID:
- `find_idempotent_entry(key, fingerprint)` returns the original entry on a matching replay and raises `ValidationError` when the key was used with different arguments.
- `record_idempotent_entry(key, fingerprint, entry)` saves the entry and the key together.

**Service (`api.py`).** `upgrade_subscription(..., *, idempotency_key)` works in this order:
1. Checks argument types: non-empty strings for the key and IDs, and real integers (not booleans) for the day counts. This comes first so that `True` can't count as a replay of `1`.
2. Looks up the key **before** the business checks. After a successful upgrade the subscription is already on the new plan, so re-running the "is this an upgrade?" check would wrongly reject a valid replay.
3. Looks up the subscription and both plans, and computes the charge.
4. Records a `plan_upgrade` entry with `reference_id=subscription_id`, then sets `subscription.plan_id` to the new plan.

All validation happens before anything is saved, so a failed call changes nothing and doesn't use up the key.

**Tests (`tests/test_subscription_upgrade.py`).**
- **Rounding:** an exact half cent rounds up (12.5 → 13, where banker's rounding would give 12), below-half and above-half cases round correctly, and tax on 82.5 cents rounds to 83.
- **Edges:** 0 days and a full cycle both price correctly, and tax uses the new plan's rate.
- **Errors:** every invalid input is rejected and leaves no entries and no plan change.
- **Idempotency:** a replay returns the same entry object with no duplicate and an unchanged balance. Reusing a key with a different plan, days, cycle length or subscription is rejected. A failed attempt doesn't use up the key, and `idempotency_key` must be passed by keyword.

Two choices to be aware of:
- Each entry's `metadata` records the old and new plan IDs and the day counts, and `reason` reads like `upgrade starter -> pro`.
- An upgrade with `days_remaining == 0` is allowed. It records a zero-cent entry and still switches the plan.

The upgrade doesn't check the subscription's `status`, because the spec didn't ask for it and nothing in the code currently changes it from `"active"`.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-1-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-1-gate-review.txt`): errors=2, warnings=0
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-1-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-1-grader.json`): passed=False
