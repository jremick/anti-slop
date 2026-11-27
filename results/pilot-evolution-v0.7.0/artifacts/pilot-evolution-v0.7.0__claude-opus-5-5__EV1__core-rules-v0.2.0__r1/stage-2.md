# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T01:38:32Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 142.39
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

Promo codes now work on both orders and plan upgrades. `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` exits 0 with 42 tests passing (22 from before plus 20 new).

**One shared pricing step.** `pricing.apply_promo_and_tax(subtotal_cents, tax_bps, *, promo, as_of)` is now the only place discounts and tax are calculated. It checks the promo, takes the discount off the pre-tax subtotal (never below 0), then taxes the discounted amount. Both `calculate_order_totals` and `calculate_upgrade_totals` go through it, so there is no separate path for orders without a promo.

**What changed**
- **`models.py`:** a new frozen `Promo` dataclass, also exported from the package.
- **`ledger.py`:** `add_promo` and `get_promo`. Asking for an unknown code raises `ValidationError`.
- **`pricing.py`:**
  - `apply_promo_and_tax` as above.
  - Strict `YYYY-MM-DD` date parsing (`2026-1-1` and `2026-02-30` are rejected).
  - Promo and code validation.
  - Totals now come back as a `PricedTotals(subtotal_cents, discount_cents, tax_cents, total_cents)` named tuple.
- **`api.py`:**
  - `register_promo(...)` validates the inputs and stores the promo.
  - `place_order` and `upgrade_subscription` take optional `promo_code` and `as_of`.
  - Orders fill in the discounted `subtotal_cents`, `discount_cents` and `promo_code`.
  - Ledger entries for both carry `discount_cents` and `promo_code` in their metadata.

**Decisions you may want to revisit**
- **Percentage discounts round half-up to the cent.** For example, 15% of 1010¢ is 151.5¢, so 152¢ comes off.
- **Comma, semicolon, `+`, `&`, `|`, `/` or any whitespace in a code is treated as stacking and rejected.** This applies when registering a code as well as when using one.
- **Codes are case-sensitive.** `pcT10` is an unknown code, not a match for `PCT10`.
- **Registering a code that already exists raises `ValidationError`** rather than replacing it. (Registering a plan that already exists still overwrites it.)
- **`expires_on` is inclusive.** A promo is still valid on its expiry date.
- **A malformed `as_of` is rejected even when no promo is given.**
- **On orders, the 500¢ legacy flat fee counts as part of the subtotal** for both the discount and the minimum-subtotal check.
- **On upgrades, the minimum-subtotal check uses the prorated amount.**
- **`promo_code` and `as_of` are part of the upgrade's idempotency check.** Replaying a key with a different promo or date raises a conflict.

**One Turn 1 test changed.** `test_upgrade_totals_use_new_plan_tax` now expects the 4-field result: `(666, 0, 55, 721)` instead of `(666, 55, 721)`. The values are the same, with a zero discount added.

**New tests** are in `tests/test_promos.py`:
- **Calculations:** percentage rounding, fixed amounts that hit zero, and the promo applied after the legacy fee but before tax.
- **Expiry:** missing date, past the expiry date, on the expiry date, and malformed dates.
- **Bad codes:** unknown, empty, wrong case, stacked or not a string.
- **Minimum subtotal:** just below and exactly at the minimum.
- **Registration:** invalid inputs and duplicate codes.
- **Upgrades with promos:** the full calculation, the minimum checked against the prorated amount, and the idempotency check including the promo.

Every rejection test also confirms that nothing was written to the ledger and the plan didn't change.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=False
