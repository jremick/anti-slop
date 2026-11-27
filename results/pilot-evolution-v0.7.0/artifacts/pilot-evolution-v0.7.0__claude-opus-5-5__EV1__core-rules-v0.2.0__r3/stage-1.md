# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3 — Stage 1/4

- Timestamp UTC: 2026-11-27T02:17:42Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 103.88
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

I added `OrderService.upgrade_subscription(...)` for mid-cycle plan upgrades. `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` exits 0, with 22 tests passing (the 4 existing ones plus 18 new). It uses only the standard library.

**How it works**
- **`pricing.py`:** two new helpers do the maths using the existing `round_half_up_div` and `compute_tax_cents`. `compute_prorated_upgrade_cents` works out the charge and rejects bad day counts and non-upgrades. `calculate_upgrade_totals` returns the charge, tax and total, with tax at the new plan's `tax_bps`.
- **`ledger.py`:** the ledger now keeps a record of each idempotency key and the arguments it was used with. A replay with the same arguments returns the original `LedgerEntry`; different arguments raise `ValidationError`. Saving a key also writes its entry, so the two can't get out of sync.
- **`api.py`:** the method checks the key, ID types and day counts first. Next it looks up the key, *before* comparing plan prices. Otherwise a replay would be wrongly rejected, because after the first call the subscription is already on the new plan. Then it records the `plan_upgrade` entry and switches `subscription.plan_id`. The entry's `metadata` holds the old and new plan, the day counts and the key.

**Choices you may want to review**
- A failed call doesn't use up its key, so the same key can be retried with corrected arguments.
- Booleans are rejected before the key lookup, so `True` can't match an earlier call made with `1`.
- `days_remaining=0` is allowed: the plan switches and the charge is 0.
- Subscription and plan IDs must be non-empty strings.
- Keys are shared across all subscriptions, not scoped to one.

**Tests** (`tests/test_upgrades.py`)
- **Rounding:** exact halves round up (e.g. 2.5¢ → 3¢, where banker's rounding gives 2¢), other fractions round to nearest, and tax halves round up too (82.5¢ → 83¢). The 0-day and full-cycle edge cases are covered.
- **Rejections:** unknown IDs, equal-price and cheaper plans, every bad day-count case, booleans and floats, and empty or non-string keys. Each case also checks that no entry was written and the plan didn't change.
- **Idempotency:** replay returns the same entry with no duplicate and an unchanged balance, and reusing a key with a different value for any of the four arguments is rejected. A new key on an already-upgraded subscription is rejected, and a key can be reused after a failed attempt.

To check the tests actually catch mistakes, I temporarily replaced half-up rounding with plain floor division (3 tests failed) and disabled the replay lookup (1 test failed). I restored the original code afterwards and the suite passes again.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3/stage-1-grader.json`): passed=False
