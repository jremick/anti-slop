# pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:23:33Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 198.89
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/__init__.py', 'benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/models.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_plan_upgrades.py', 'benchmarks/sources/ev1_order_ledger/tests/test_promos.py']
- Workspace deleted: []

## Prompt

Implement Turn 2 (promo codes across both orders and upgrades without duplicating pricing logic):
- Add `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)` validating exactly one of `percent_off` (1..100) or `amount_off_cents` (>0), non-negative `min_subtotal_cents`, and non-empty `code`.
- Add optional `promo_code=None` and `as_of=None` (`YYYY-MM-DD`) to both `place_order` and `upgrade_subscription`, delegating discount + tax calculation to one shared canonical helper in `pricing.py`.
- Apply discount to pre-tax subtotal (clamped at 0), compute tax on the discounted subtotal, and set `Order.subtotal_cents` to the discounted subtotal with `Order.discount_cents` and `Order.promo_code` populated.
- Fail closed with `ValidationError` (never silently returning 0 discount) on unknown codes, multi-code strings (e.g., `'A,B'`), subtotals below `min_subtotal_cents`, or expiring promos where `as_of` is missing or `as_of > expires_on`.
- Add unit tests for percentage/fixed promos, expiry/stacking rejection, minimum subtotal, and upgrade+promo calculation, then run `run_checks.py`.

## Raw Model Output

Implemented Turn 2 (promo codes across both orders and mid-cycle plan upgrades via a single shared pricing helper) in `benchmarks/sources/ev1_order_ledger/`:

### Changes
- **[models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py)** & **[__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py)**: Added and exported frozen `PromoCode` dataclass (`code`, `percent_off`, `amount_off_cents`, `expires_on`, `min_subtotal_cents`).
- **[pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py)**:
  - Added strict `parse_iso_date` (`YYYY-MM-DD`), `validate_promo_code_str` (rejecting empty/whitespace/multi-code delimiters `,`, `;`, `+`, `|`, and non-strings), and `validate_promo_code` (enforcing exactly one of `percent_off` in `1..100` or `amount_off_cents > 0`, non-negative `min_subtotal_cents`, and valid `expires_on`).
  - Added shared canonical helper `apply_promo_and_tax(subtotal_cents, tax_bps, *, promo=None, as_of=None)` used across orders and plan upgrades: enforces expiry (`as_of` required and `as_of <= expires_on`) and `min_subtotal_cents`, applies exact integer half-up percentage or fixed discount clamped at `0`, and computes tax on the discounted subtotal.
  - Added `compute_order_subtotal_cents` and routed `calculate_order_totals` and `calculate_plan_upgrade_totals` through `apply_promo_and_tax`.
- **[ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py)**: Added `add_promo` and `get_promo` to `OrderLedger`, failing closed with `ValidationError` on invalid, stacked, or unknown codes.
- **[api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py)**:
  - Added `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Added optional `promo_code=None` and `as_of=None` to both `place_order` and `upgrade_subscription`, delegating discount and tax calculation to `apply_promo_and_tax`, populating `Order.subtotal_cents` (discounted), `Order.discount_cents`, and `Order.promo_code`, and including `promo_code`/`as_of` in the `upgrade_subscription` idempotency fingerprint.
- **[test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)**: Added unit tests covering `register_promo` validation, percentage half-up and clamped fixed promos, fail-closed rejection on unknown/stacked/expired/below-min codes, and upgrade + promo + idempotency behavior.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` — **17 tests ran, OK (exit code 0)**.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=False
