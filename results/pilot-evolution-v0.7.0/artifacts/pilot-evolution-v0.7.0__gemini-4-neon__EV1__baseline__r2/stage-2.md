# pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T03:25:28Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 195.67
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

Implemented Turn 2 (promo codes across orders and mid-cycle plan upgrades via a single shared pricing helper):

### Changes
- **Model & exports** ([models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py#L25-L31), [__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py#L5-L18)):
  - Added frozen dataclass `Promo` and exported it from the package.
- **Canonical pricing & promo validation** ([pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py#L52-L197)):
  - Added `parse_iso_date`, `validate_promo_code`, `validate_promo`, and the shared canonical `apply_promo_and_tax(gross_subtotal_cents, tax_bps, *, promo=None, as_of=None)` helper.
  - Both `calculate_order_pricing` and `calculate_prorated_upgrade_pricing` (as well as the existing `calculate_order_totals` / `calculate_prorated_upgrade_totals`) delegate to `apply_promo_and_tax`, applying pre-tax discounts (clamped at `0`) before computing tax on the discounted subtotal.
- **Ledger storage** ([ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py#L44-L55)):
  - Added `OrderLedger.add_promo` and `OrderLedger.get_promo`, failing closed with `ValidationError` on invalid, stacked, or unknown codes.
- **Service API** ([api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py#L23-L186)):
  - Added `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Extended `place_order` and `upgrade_subscription` with optional `promo_code=None` and `as_of=None`; populated `Order.subtotal_cents` (discounted), `Order.discount_cents`, and `Order.promo_code`; included `(promo_code, as_of)` in `upgrade_subscription`'s idempotency fingerprint.
- **Unit tests** ([test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)):
  - Added tests for promo registration validation, percentage and fixed promos (including 0-clamping and `legacy_flat_fee`), expiry/`as_of` boundaries, minimum subtotal, unknown/stacked code rejection, and upgrade + promo pricing + idempotency.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` — **19/19 tests passed** (exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r2/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r2/stage-2-grader.json`): passed=False
