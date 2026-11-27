# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T01:51:50Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 145.27
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/__init__.py', 'benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/models.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_promos.py', 'benchmarks/sources/ev1_order_ledger/tests/test_subscription_upgrade.py']
- Workspace deleted: []

## Prompt

Implement Turn 2 (promo codes across both orders and upgrades without duplicating pricing logic):
- Add `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)` validating exactly one of `percent_off` (1..100) or `amount_off_cents` (>0), non-negative `min_subtotal_cents`, and non-empty `code`.
- Add optional `promo_code=None` and `as_of=None` (`YYYY-MM-DD`) to both `place_order` and `upgrade_subscription`, delegating discount + tax calculation to one shared canonical helper in `pricing.py`.
- Apply discount to pre-tax subtotal (clamped at 0), compute tax on the discounted subtotal, and set `Order.subtotal_cents` to the discounted subtotal with `Order.discount_cents` and `Order.promo_code` populated.
- Fail closed with `ValidationError` (never silently returning 0 discount) on unknown codes, multi-code strings (e.g., `'A,B'`), subtotals below `min_subtotal_cents`, or expiring promos where `as_of` is missing or `as_of > expires_on`.
- Add unit tests for percentage/fixed promos, expiry/stacking rejection, minimum subtotal, and upgrade+promo calculation, then run `run_checks.py`.

## Raw Model Output

Turn 2 is done: promo codes now work on both `place_order` and `upgrade_subscription`, and one shared helper does all the discount and tax maths. `run_checks.py` exits 0 with 42 tests passing (the 19 earlier ones unchanged, plus 23 new).

**Shared pricing (`pricing.py`).**
- **One helper:** `price_charge(gross_subtotal_cents, tax_bps, *, promo, as_of)` takes the discount off the pre-tax subtotal (never below 0) and then taxes what's left. It returns all the amounts: gross, discount, discounted subtotal, tax and total.
- **Discount rules:** `compute_discount_cents` checks expiry first (a missing `as_of`, or one after `expires_on`, is rejected), then the minimum subtotal. Percentage discounts round half-up, and fixed discounts are capped at the subtotal.
- **Validation:** `build_promo` checks a new promo's settings, `validate_promo_code` rejects multi-code strings like `A,B`, `A;B`, `A B` and `A+B`, and `parse_iso_date` accepts only real `YYYY-MM-DD` dates.
- **Inputs:** orders and upgrades now each have a function that works out the pre-discount amount (`compute_order_gross_cents` and `compute_upgrade_gross_cents`). Both feed into `price_charge`.
- **Existing functions:** `calculate_order_totals` and `compute_upgrade_proration` still return the same three values as before, but now just call the functions above. Nothing in the service uses them any more; I kept them because they were already public and the Turn 1 tests call `compute_upgrade_proration`.

**Ledger and models.** There's a new frozen `Promo` model, exported from the package. `OrderLedger` gains `add_promo` and `get_promo`; an unknown code raises `ValidationError`.

**Service (`api.py`).**
- **`register_promo`:** validates the promo as specified and returns it.
- **`place_order`:** sets `subtotal_cents` to the discounted subtotal and fills in `discount_cents` and `promo_code`.
- **`upgrade_subscription`:** charges the prorated amount after the discount, taxed at the new plan's rate.
- **Ledger entries:** when a promo is used, both kinds of entry record the code, the pre-discount amount and the discount in their metadata.
- **Idempotency:** the record of an upgrade's arguments now includes `promo_code` and `as_of`. Reusing a key with a different promo or date is rejected, and an exact replay still returns the original entry even if the promo has since expired.
- **Failures:** any rejected request records nothing, leaves the subscription's plan unchanged and doesn't use up the idempotency key.

**Tests (`tests/test_promos.py`).**
- **Shared helper:** half-up rounding, the cap at 0, and expiry being allowed on the expiry date itself.
- **Registering promos:** 20 invalid setups are rejected.
- **Orders:** percentage, fixed and over-large fixed discounts, a promo combined with the legacy flat fee, the minimum subtotal, expiry, and unknown, combined or badly formed codes and dates.
- **Upgrades:** percentage and fixed promos, an upgrade and an order with the same amount pricing identically, failures leaving nothing changed, and replay and conflict checks that include the promo and date.

Some behaviour goes beyond what you specified:
- **Duplicate codes:** registering an existing promo code again raises `ValidationError` instead of replacing it.
- **Case and characters:** codes are case-sensitive (`save10` doesn't match `SAVE10`) and may contain only letters, digits, `_` and `-`.
- **Dates:** `expires_on` must be a `YYYY-MM-DD` string; a `date` object is rejected. A bad `as_of` is rejected even when no promo code is given.
- **Minimum subtotal:** checked against the amount before the discount. For upgrades that is the prorated amount.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-2-gate-review.txt`): errors=0, warnings=1
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-2-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r2/stage-2-grader.json`): passed=False
