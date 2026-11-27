# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2 — Stage 1/4

- Timestamp UTC: 2026-11-27T02:03:25Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 73.86
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

I added `OrderService.upgrade_subscription(...)` and its tests. `python3 run_checks.py` exits 0 with 19 tests passing: the 4 existing ones plus 15 new ones.

**Where the code went**
- **`pricing.py`**: two new helpers. `validate_proration_window` rejects booleans, non-integers, `cycle_days <= 0`, `days_remaining < 0` and `days_remaining > cycle_days`. `calculate_upgrade_proration` rejects non-upgrades, prorates the price difference with `round_half_up_div`, and taxes it with `compute_tax_cents` at the new plan's `tax_bps`.
- **`ledger.py`**: idempotency is stored here. `lookup_idempotent_entry` returns the original entry on a matching replay and raises `ValidationError` if the same key comes with different arguments. `record_idempotent_entry` records the entry and saves the key together.
- **`api.py`**: `upgrade_subscription` does the input checks, then the replay lookup, then looks up the IDs and calculates the charge. Only then does it change anything: it records a `plan_upgrade` entry with `reference_id=subscription_id` and updates `subscription.plan_id`.

**Decisions you may want to revisit**
- **Replay check comes before the upgrade check.** It has to: after the first call the subscription is already on the new plan, so checking again would reject a legitimate replay as a non-upgrade.
- **Bad values are rejected before the replay check.** So `True` can't be mistaken for an earlier request that used `1` (Python treats `True == 1` as equal).
- **A failed call doesn't use up its key.** If a call is rejected, the same key can be retried with corrected arguments.
- **Extra entry details.** Each entry gets a `reason` and `metadata` showing the old and new plan, the days and the key.
- **IDs must be non-empty strings.** Other values raise `ValidationError`.

**Tests (`tests/test_upgrades.py`)**
- **Rounding:** an exact half rounds up (7.5 → 8, 0.5 → 1), just below half rounds down (0.48 → 0), and tax rounds half-up at the new plan's rate. Zero days remaining and a full cycle are covered.
- **Rejected input:** unknown IDs; same-priced and cheaper plans; each invalid day bound; booleans, floats, strings and `None` for the day counts; empty or non-string keys. Each case also checks that no entry was recorded and the plan didn't change.
- **Idempotency:** a replay returns the same entry without adding one; reusing a key with any changed argument raises and changes nothing; separate keys allow back-to-back upgrades; `True` doesn't match an earlier `1`.

To confirm the tests catch real bugs, I temporarily broke the code twice. Switching to round-down division made 4 tests fail, and turning off the replay lookup made 1 test error. I restored both files and the suite passes again.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2/stage-1-grader.json`): passed=False
