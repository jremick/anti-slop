# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:05:35Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 128.50
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/models.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_promos.py', 'benchmarks/sources/ev1_order_ledger/tests/test_upgrades.py']
- Workspace deleted: []

## Prompt

Implement Turn 2 (promo codes across both orders and upgrades without duplicating pricing logic):
- Add `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)` validating exactly one of `percent_off` (1..100) or `amount_off_cents` (>0), non-negative `min_subtotal_cents`, and non-empty `code`.
- Add optional `promo_code=None` and `as_of=None` (`YYYY-MM-DD`) to both `place_order` and `upgrade_subscription`, delegating discount + tax calculation to one shared canonical helper in `pricing.py`.
- Apply discount to pre-tax subtotal (clamped at 0), compute tax on the discounted subtotal, and set `Order.subtotal_cents` to the discounted subtotal with `Order.discount_cents` and `Order.promo_code` populated.
- Fail closed with `ValidationError` (never silently returning 0 discount) on unknown codes, multi-code strings (e.g., `'A,B'`), subtotals below `min_subtotal_cents`, or expiring promos where `as_of` is missing or `as_of > expires_on`.
- Add unit tests for percentage/fixed promos, expiry/stacking rejection, minimum subtotal, and upgrade+promo calculation, then run `run_checks.py`.

## Raw Model Output

Promo codes now work for both orders and upgrades. `run_checks.py` exits 0 with 37 tests passing: 4 original, 15 from Turn 1 and 18 new.

**How it fits together**
- **One pricing function:** `price_charge(pre_discount_subtotal, tax_bps, promo=, as_of=)` in `pricing.py` handles every discount and tax calculation. Both order pricing and upgrade proration call it, so the logic exists in one place. It applies the discount to the pre-tax subtotal, stops the subtotal at 0, computes tax on the discounted amount, and returns `Charge(subtotal_cents, discount_cents, tax_cents, total_cents)`.
- **`register_promo`:** the checks live in `pricing.build_promo`. A new `Promo` model is in `models.py`, and the ledger stores promos.
- **`place_order`:** the order's `subtotal_cents` is now the discounted subtotal, and `discount_cents` and `promo_code` are filled in. Both order and upgrade ledger entries record the promo code and discount in `metadata`.
- **`upgrade_subscription`:** the promo code and `as_of` are now part of what a replay must match. A replay returns the original entry, and the same key with a different promo or date raises `ValidationError`.

**Changes to existing code**
- `calculate_order_totals` and `calculate_upgrade_proration` now return `Charge` instead of a 3-tuple.
- So I changed the 8 expected values in the Turn 1 pricing tests from 3-tuples to `Charge(...)`. Every number is the same; only `discount_cents=0` was added.

**Decisions you may want to revisit**
- **Code format:** codes are letters, digits, `_` and `-` only. That's how `"A,B"`, `"A B"`, `"A+B"` and codes with surrounding spaces get rejected as more than one code, rather than just looked up.
- **Exact matching:** codes are case-sensitive, so `pct10` doesn't match `PCT10`.
- **Re-registering a code raises an error** instead of quietly replacing its terms.
- **Dates:** `expires_on` is the last valid day, so a promo still works on that day. Dates must be exactly `YYYY-MM-DD`, and invalid ones like `2026-02-30` are rejected.
- **What the minimum is checked against:** for orders, the subtotal before discount and including the legacy flat fee. For upgrades, the prorated amount before discount.
- **Percentage discounts** round half-up to the cent; for example, 10% of 1005 is 101.

**Tests (`tests/test_promos.py`)**
- **Registration:** valid and invalid inputs.
- **Percentage and fixed promos:** including half-up rounding, stopping the subtotal at 0, and the legacy flat fee.
- **Minimum subtotal:** 1999 against a 2000 minimum is rejected; exactly 2000 is accepted.
- **Expiry:** missing `as_of`, the day after expiry, the expiry day itself, and badly formatted dates.
- **Stacked and unknown codes:** combined codes in different formats are rejected.
- **Upgrades with promos:** the prorated subtotal of 1000 becomes 900 + 74 tax = 974 with 10% off, and 700 + 58 = 758 with 300 off.
- **Nothing changes on failure:** a rejected upgrade leaves the subscription's plan unchanged, records nothing, and doesn't use up the key.
- **Replay and conflict:** checked with the promo arguments included.

I also broke the code on purpose 7 ways, restoring it each time. All 7 made tests fail:
- an expired promo was accepted;
- a missing `as_of` was allowed;
- the minimum subtotal was skipped;
- tax was charged on the amount before discount;
- the subtotal could go below 0;
- any code format was accepted;
- the promo arguments were left out of the replay check.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=False
