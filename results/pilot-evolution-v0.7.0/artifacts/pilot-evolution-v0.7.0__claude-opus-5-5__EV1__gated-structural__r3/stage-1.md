# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3 — Stage 1/4

- Timestamp UTC: 2026-11-27T02:10:17Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 90.00
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

Turn 1 is done. `upgrade_subscription` is in place, and `python3 run_checks.py` passes all 21 tests (the 4 that were there before plus 17 new ones) and exits 0. Everything is stdlib only.

**What I added**
- **`pricing.py`**:
  - `validate_proration_window(days_remaining, cycle_days)` checks the bounds. It uses the existing validators, so booleans and non-integers are rejected.
  - `calculate_upgrade_proration(old_plan, new_plan, days_remaining, cycle_days)` returns `(subtotal, tax, total)`. The subtotal is `round_half_up_div((new - old) * days_remaining, cycle_days)` and the tax is `compute_tax_cents(subtotal, new_plan.tax_bps)`. It raises `ValidationError` if the new plan doesn't cost more than the old one.
- **`ledger.py`**: a store that maps each idempotency key to the request's arguments and the entry ID it produced.
  - `find_idempotent_entry` returns the earlier entry for a key, or raises `ValidationError` if the key was used with different arguments.
  - `record_idempotent_entry` saves the entry and the key together.
- **`api.py`**: `OrderService.upgrade_subscription(...)` runs in this order:
  1. Checks argument types and bounds: the IDs and key must be non-empty strings, and booleans are rejected.
  2. Checks for a replay or a conflicting reuse of the key.
  3. Looks up the subscription and both plans; unknown IDs raise `ValidationError`.
  4. Calculates the charge, records a `plan_upgrade` entry with `reference_id=subscription_id` (the old and new plan IDs go in the entry's metadata), and only then updates `subscription.plan_id`.

**Behaviour you might not expect**
- **Replays are checked before the plans are looked up.** After a successful upgrade the subscription is already on the new plan, so recomputing on replay would wrongly reject it as "not an upgrade".
- **Argument checks still run before the replay lookup.** In Python `True == 1`, so without this a replay with `days_remaining=True` would match an earlier call with `1` and be accepted.
- **A failed call doesn't use up its key**, so the same key can be retried after fixing the arguments.
- **`days_remaining=0` is allowed** and records an entry for 0 cents.

**New tests (`tests/test_upgrades.py`)**
- **Rounding:** an exact half-cent rounds up (2.5 → 3), fractions above and below half go the right way, a half-cent of tax rounds up (82.5 → 83), tax uses the new plan's rate, and the 0-day and full-cycle edges.
- **End to end:** the entry's fields, the plan switch, the account statement, and two upgrades in a row (the second is prorated from the plan the first one moved to).
- **Rejections:** unknown IDs, same-price and cheaper plans, every bound violation, booleans, floats, and empty, blank or `None` keys. Each check also confirms nothing was recorded and the plan didn't change.
- **Idempotency:** a replay returns the same entry object and adds no new entry. Reusing a key with any changed argument, including a different subscription, raises `ValidationError`. A boolean replay is not treated as a match, and different keys don't affect each other.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-1-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-1-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-1-grader.json`): passed=False
