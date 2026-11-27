# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T01:58:38Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 140.49
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/__init__.py', 'benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/models.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
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

I've added promo codes to both orders and upgrades. `run_checks.py` exits 0 with 62 tests passing: the 31 from before plus 31 new ones in `tests/test_promos.py`.

**How it fits together**
- **One shared calculation.** `pricing.price_charge(gross_subtotal, *, tax_bps, promo=None, as_of=None)` is the only place discounts and tax are worked out. It takes the discount off the pre-tax subtotal, never going below 0, then taxes what's left. It returns a `PricedCharge` with the gross amount, discount, discounted subtotal, tax, total and code.
  - `price_order` and `price_upgrade` just work out the gross amount (line items plus the legacy fee, or the prorated upgrade) and pass it to `price_charge`.
  - The existing `calculate_order_totals` and `calculate_upgrade_totals` still return the same 3-tuple, now by calling these functions.
- **Rounding.** Percentage discounts use the same half-up integer division as proration, and fixed-amount discounts are capped at the subtotal.
- **Registering a promo.** `OrderService.register_promo(...)` checks the arguments (in `pricing.build_promo`), creates a frozen `Promo` (new in `models.py`) and stores it in the ledger.
- **Orders.** `Order.subtotal_cents` is the discounted amount, with `discount_cents` and `promo_code` filled in. The ledger entry's metadata also records the code, the pre-discount amount and the discount.
- **Upgrades.** They take `promo_code` and `as_of` and record the same metadata. Both arguments count towards idempotency, so retrying with the same key but a different promo or date raises `ValidationError`. Like the plan check, promo expiry isn't re-checked on a retry, so a retry after the promo expires still returns the original entry.

**What gets rejected with `ValidationError`.** A rejected call creates no order or entry, leaves the plan unchanged, uses up no ID number and doesn't reserve the idempotency key:
- **Unknown codes.**
- **More than one code.** Any separator (`,` `;` `+` `|` `/` `&` or whitespace) is rejected as stacking. Anything else outside `[A-Za-z0-9_-]` is rejected as malformed.
- **Below the minimum.** The minimum is compared with the amount before the discount: for orders that includes the legacy fee, for upgrades it's the prorated amount.
- **Expiring promos with no `as_of`, or with `as_of` after the expiry date.**
- **Badly formatted dates.** Dates must be strict `YYYY-MM-DD` with ASCII digits only, so `20260101` and `2026-02-30` both fail. A bad `as_of` is rejected even when no promo is given.

**Decisions you may want to change**
- **Registering a code a second time is rejected.** Silently replacing it would change prices for anyone already using it.
- **Codes are case-sensitive.** `pct10` doesn't match `PCT10`.
- **The expiry date is inclusive.** A promo can still be used on its `expires_on` date.
- **A discount can legitimately come out as 0.** For example, 1% of 10¢ rounds to 0, or an upgrade with 0 days remaining. That is a valid result, not a failure.

**Test coverage includes:**
- Percentage discounts rounding half-up, and fixed discounts capped at the subtotal.
- Tax charged on the discounted amount, and the legacy fee being discounted too.
- The minimum-subtotal and expiry boundaries, missing `as_of`, and 13 stacked or malformed codes.
- Every invalid registration case.
- Upgrades with each kind of promo, and retries and conflicting reuse of a key with promos.
- A check that the same amount, promo and tax rate give the same figures for an order and an upgrade.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r2/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r2/stage-2-grader.json`): passed=False
