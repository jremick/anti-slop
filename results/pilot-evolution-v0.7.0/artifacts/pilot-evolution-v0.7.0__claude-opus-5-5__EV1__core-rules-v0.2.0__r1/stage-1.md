# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1 — Stage 1/4

- Timestamp UTC: 2026-11-27T01:36:09Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 68.69
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

I've added mid-cycle prorated plan upgrades with idempotency. `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` exits 0, with 22 tests passing (the 4 that were already there plus 18 new ones). It uses only the standard library.

**What changed**
- **`pricing.py`:** two new helpers.
  - `compute_proration_cents(...)` checks the inputs (rejecting booleans, negative values and `days_remaining > cycle_days`), rejects any change where the new plan doesn't cost more, then uses the existing `round_half_up_div`.
  - `calculate_upgrade_totals(old_plan, new_plan, days_remaining, cycle_days)` returns the subtotal, tax and total. Tax comes from `compute_tax_cents(subtotal, new_plan.tax_bps)`.
- **`ledger.py`:** a store of idempotency keys.
  - `get_idempotent_entry(key, fingerprint)` returns the original entry if the key was used with the same arguments, `None` if the key is new, and raises `ValidationError` if it was used with different arguments.
  - `record_idempotent_entry(...)` records the entry and the key together.
- **`api.py`:** `OrderService.upgrade_subscription(...)`.
  - It first checks argument types: the IDs and the key must be non-empty strings, and the day counts must be real integers.
  - Next it checks the idempotency key, and only then the business rules. That order is needed: after a successful upgrade the subscription is already on the new plan, so a replay checked against the rules first would wrongly fail as "not an upgrade".
  - All checks and calculations happen before anything is written, so a rejected call adds no ledger entry and leaves the plan unchanged.
  - It records a `plan_upgrade` entry whose `reference_id` is the subscription ID. The entry's metadata holds the old and new plan, the day counts and the key.

**Behaviour you might not assume**
- **Failed calls don't use up the key.** A call rejected by validation can be retried with the same key.
- **Keys are global.** One key can't be reused across different subscriptions.
- **`days_remaining == 0` is allowed.** It records a zero-amount entry and still switches the plan.
- **Subscription status isn't checked.** A non-`active` subscription can still be upgraded, since the request didn't specify a rule for that.

**Tests** are in `tests/test_upgrades.py`:
- **Rounding:** exact half (0.5 → 1, 1.5 → 2), just below and above half (33.3 → 33, 66.7 → 67), 0 and the full number of days, and tax taken from the new plan.
- **Full calls:** the resulting entry, the account balance and the new plan.
- **Rejections:** unknown IDs, a cheaper plan, the same price or the same plan, out-of-range days, booleans and floats, and an empty, blank or `None` key. Each of these also checks that no entry was added and the plan didn't change.
- **Idempotency:** a replay returns the same entry object with no duplicate. Reusing a key with a different plan, different days, a different cycle length or a different subscription raises an error, and so does a new key once the subscription is already on that plan.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1/stage-1-grader.json`): passed=False
