# pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T03:36:08Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 190.57
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

Implemented Turn 2 (promo codes across orders and mid-cycle upgrades via a shared canonical pricing helper):

- **Domain model & exports** ([models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py), [__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py)):
  - Added frozen `Promo` dataclass and exported it from the package.
- **Shared canonical promo + tax helper** ([pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py)):
  - Added `parse_iso_date`, `validate_promo_code`, `validate_promo`, and the single shared helper `apply_promo_and_tax(subtotal_cents, *, tax_bps=0, promo=None, as_of=None)`.
  - Enforces single-code syntax (rejecting empty, whitespace, and multi-code separators like `,`, `;`, `+`, `|`), exact `YYYY-MM-DD` dates, required `as_of` and `as_of <= expires_on` for expiring promos, `subtotal_cents >= min_subtotal_cents`, half-up percentage rounding (`1..100`) or fixed `amount_off_cents` (`> 0`), pre-tax clamping at `0`, and tax calculation on the discounted subtotal.
  - Wired both `calculate_order_pricing` / `calculate_order_totals` and `calculate_upgrade_pricing` / `calculate_upgrade_totals` through `apply_promo_and_tax`.
- **Ledger & service integration** ([ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py), [api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py)):
  - Added `OrderLedger.add_promo` / `get_promo` and `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Added optional `promo_code=None` and `as_of=None` to `OrderService.place_order` and `OrderService.upgrade_subscription` (including `promo_code` and `as_of` in the upgrade idempotency fingerprint), setting `Order.subtotal_cents` to the discounted subtotal with `Order.discount_cents` and `Order.promo_code` populated.
- **Unit tests** ([test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)):
  - Added tests covering `register_promo` validation, percentage & fixed promos, clamping to `0`, expiry & missing/malformed `as_of`, multi-code/stacking & unknown code rejection, minimum subtotal enforcement, and upgrade + promo + idempotency behavior.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` — **18 tests passed (`OK`, exit code `0`)**.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r3/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r3/stage-2-grader.json`): passed=False
