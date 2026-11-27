# pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2 — Stage 1/4

- Timestamp UTC: 2026-11-27T03:12:13Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 197.25
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

Implemented Turn 1 (mid-cycle prorated plan upgrades and idempotency, stdlib only) in `benchmarks/sources/ev1_order_ledger/`:

### Changes
- **[pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py)**: Added canonical helpers `validate_proration_window`, `compute_prorated_upgrade_cents`, and `calculate_upgrade_totals` computing exact integer-cent half-up proration via `round_half_up_div((new_plan.monthly_cents - old_plan.monthly_cents) * days_remaining, cycle_days)` and tax via `compute_tax_cents(subtotal, new_plan.tax_bps)`, rejecting non-upgrades, invalid bounds, and booleans/non-integers with `ValidationError`.
- **[ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py)**: Added canonical idempotency helpers on `OrderLedger` (`validate_idempotency_key`, `lookup_idempotent_entry`, `record_idempotent_entry`) using type-aware request fingerprints so identical replays return the original `LedgerEntry` without duplicating entries and conflicting arguments (including `bool` vs `int`) raise `ValidationError`.
- **[api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py)**: Added `OrderService.upgrade_subscription(subscription_id, new_plan_id, days_remaining, cycle_days, *, idempotency_key)` coordinating input validation, idempotency lookup/recording, proration/tax computation, `subscription.plan_id` update, and `LedgerEntry` creation (`kind="plan_upgrade"`, `reference_id=subscription_id`).
- **[test_upgrades.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_upgrades.py)**: Added unit tests covering exact half-up proration and tax rounding, `0` and full-cycle boundary windows, unknown IDs, non-upgrades, invalid bounds, booleans/non-ints, empty keys, idempotent replays (including after subsequent upgrades), and idempotency conflicts.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py`: **11 tests passed (`OK`, exit code 0)** (4 baseline tests in [test_orders.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_orders.py) + 7 new tests in [test_upgrades.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_upgrades.py)).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2/stage-1-grader.json`): passed=False
