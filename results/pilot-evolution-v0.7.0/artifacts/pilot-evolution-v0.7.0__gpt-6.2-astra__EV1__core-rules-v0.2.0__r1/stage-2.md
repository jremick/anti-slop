# pilot-evolution-v0.7.0__gpt-6.2-astra__EV1__core-rules-v0.2.0__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T01:40:13Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 84.29
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

Implemented promo codes for orders and subscription upgrades using one shared pricing helper. Percentage discounts round half-up to the nearest cent. Fixed discounts are capped at the pre-tax subtotal, and tax is calculated after the discount. Upgrades apply the promo after proration and include both `promo_code` and `as_of` in idempotency checks.

Unknown, stacked, expired, or ineligible codes raise `ValidationError` before any charge is recorded. Expiring promos require an explicit date and remain valid through their expiry date.

`python3 benchmarks/sources/ev1_order_ledger/run_checks.py` exited 0. All 15 tests passed, including five new promo tests.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gpt-6.2-astra__EV1__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gpt-6.2-astra__EV1__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=False
