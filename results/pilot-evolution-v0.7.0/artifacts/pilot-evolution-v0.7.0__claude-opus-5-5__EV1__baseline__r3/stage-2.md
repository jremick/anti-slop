# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:26:20Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 125.38
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/models.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_plan_upgrade.py', 'benchmarks/sources/ev1_order_ledger/tests/test_promos.py']
- Workspace deleted: []

## Prompt

Implement Turn 2 (promo codes across both orders and upgrades without duplicating pricing logic):
- Add `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)` validating exactly one of `percent_off` (1..100) or `amount_off_cents` (>0), non-negative `min_subtotal_cents`, and non-empty `code`.
- Add optional `promo_code=None` and `as_of=None` (`YYYY-MM-DD`) to both `place_order` and `upgrade_subscription`, delegating discount + tax calculation to one shared canonical helper in `pricing.py`.
- Apply discount to pre-tax subtotal (clamped at 0), compute tax on the discounted subtotal, and set `Order.subtotal_cents` to the discounted subtotal with `Order.discount_cents` and `Order.promo_code` populated.
- Fail closed with `ValidationError` (never silently returning 0 discount) on unknown codes, multi-code strings (e.g., `'A,B'`), subtotals below `min_subtotal_cents`, or expiring promos where `as_of` is missing or `as_of > expires_on`.
- Add unit tests for percentage/fixed promos, expiry/stacking rejection, minimum subtotal, and upgrade+promo calculation, then run `run_checks.py`.

## Raw Model Output

Turn 2 is in. `run_checks.py` exits 0 with 44 tests passing: the 21 from before plus 23 new ones in `tests/test_promos.py`.

**One shared pricing path**
- **`pricing.apply_promo_and_tax(gross_subtotal, tax_bps, *, promo, as_of)`** is the only place discount and tax are worked out. It takes the discount off the pre-tax subtotal and never lets it go below 0. A percentage discount rounds half-up to the nearest cent. Tax is then charged on the discounted amount. It returns `PricedTotals(subtotal_cents, discount_cents, tax_cents, total_cents)`.
- **Orders:** `calculate_order_totals` adds up the items and the legacy flat fee, then passes the total to that helper.
- **Upgrades:** the Turn 1 proration math now lives in `compute_prorated_upgrade_cents`. `compute_upgrade_proration` takes that amount and passes it to the same helper, using the new plan's tax rate.
- **Promo checks** (`build_promo`, `validate_promo_code`, `parse_iso_date`) are also in `pricing.py`. `OrderService` just looks the code up and calls the helper.

**What changed outside pricing**
- `models.py` has a new frozen `Promo` dataclass.
- `ledger.py` gained `add_promo` and `get_promo`.
- `place_order` now fills in `Order.subtotal_cents` (after discount), `discount_cents` and `promo_code`. Upgrade entries record `discount_cents` and `promo_code` in their metadata.
- The idempotency check now includes `promo_code` and `as_of`. Reusing a key with a different promo, or with and without one, is rejected.

**Rejection rules I chose** (all raise `ValidationError`)
- **Stacked codes:** any code containing `,`, `;`, `+`, `|` or whitespace is treated as an attempt to combine codes and rejected, both when registering and when used. Leading spaces count, so `" SAVE20"` is rejected rather than quietly trimmed.
- **Case-sensitive codes:** `save20` won't match `SAVE20`.
- **Registering a code twice is rejected**, so an existing promo can't be silently replaced.
- **Expiry includes the last day:** `as_of == expires_on` still works. `as_of` is only required when the promo has an expiry date.
- **Dates must be exactly `YYYY-MM-DD`**, and a malformed `as_of` is rejected even when no promo is given.
- **The minimum subtotal is checked before the discount.** For upgrades, that means the prorated amount.
- **A failed call leaves nothing behind:** no order, no ledger entry, no plan change, and the idempotency key can still be used.

**One change to existing tests:** `compute_upgrade_proration` now returns 4 values instead of 3, so I added a `0` discount to the expected tuples in `test_plan_upgrade.py`. The numbers themselves didn't change. Any other code that unpacks that function's result into three values will need the same update.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r3/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r3/stage-2-grader.json`): passed=False
