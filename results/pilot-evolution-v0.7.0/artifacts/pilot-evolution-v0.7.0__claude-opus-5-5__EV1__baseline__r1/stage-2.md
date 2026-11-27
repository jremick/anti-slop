# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T01:44:27Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 131.86
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

Turn 2 is in place: promo codes now work on both orders and upgrades, and `run_checks.py` exits 0 with 49 tests passing (24 earlier plus 25 new).

**One pricing path (`pricing.py`)**
- **Shared helper:** `price_with_promo(gross_subtotal_cents, tax_bps, *, promo, as_of)` is the only place discount and tax are calculated. It takes the discount off the pre-tax subtotal (never below 0), then computes tax on what's left. It returns `PricedTotals`, which holds the subtotal before and after the discount, the discount, tax, total and the promo code.
- **Orders and upgrades:** `price_order` and `price_upgrade` each work out their own pre-discount subtotal (line items plus any legacy fee, or the prorated difference), then hand off to the shared helper. The old `calculate_order_totals` and `calculate_upgrade_totals` still exist with the same signatures, but now just call these.
- **Discount rules:** percentage discounts round half-up to the cent, and fixed discounts are capped at the subtotal. The minimum-spend check uses the subtotal before the discount: for upgrades that's the prorated amount, and for orders it includes the legacy fee.
- **Validation helpers:** `build_promo`, `validate_promo_code`, `parse_iso_date` and `compute_discount_cents` hold the checks. Instead of ever applying a $0 discount, they raise `ValidationError` for:
  - unknown codes
  - strings holding more than one code (`,`, `;`, `+`, `|`, `/` or whitespace)
  - subtotals below the minimum
  - an expiring promo with no `as_of`, or with `as_of` after the expiry date

**Service and storage**
- `register_promo(...)` checks the definition and stores a frozen `Promo` (now exported from the package).
- `place_order` fills in `Order.discount_cents` and `Order.promo_code`, and sets `subtotal_cents` to the discounted amount.
- When a promo is used, the ledger entry's metadata records the code, the subtotal before discount and the discount.
- For upgrades, `promo_code` and `as_of` are now part of the idempotency check. Reusing a key with a different promo is rejected, while replaying the exact same call after the promo has expired still returns the original entry.

**Tests (`tests/test_promos.py`)** cover:
- percentage and fixed discounts, including half-up rounding and the cap at 0
- tax calculated on the discounted amount, and the legacy fee combined with a promo
- the minimum-spend boundary for both orders and upgrades
- the expiry date itself still counting as valid, the day after failing, and a missing `as_of` failing
- multi-code strings, unknown codes and wrong-case codes rejected, with nothing recorded
- invalid promo definitions and duplicate codes rejected
- upgrade replays and conflicts when a promo is involved

Choices I made that you didn't specify — easy to change if you want different behaviour:
- **Exact-case codes:** `"save10"` won't match `"SAVE10"`. Codes may only use letters, digits, `_` and `-`.
- **Duplicate codes:** registering an existing code again raises an error rather than overwriting it, so a promo already in use can't be quietly changed. Plans, by contrast, are overwritten.
- **Strict dates:** `expires_on` and `as_of` must be `YYYY-MM-DD` strings, and Python `date` objects are rejected. `as_of` is format-checked even when no promo is given.
- **Expiry day:** a promo is still valid on its expiry date and fails from the next day.
- **No usage limits:** a code can be used any number of times; there are no per-account limits.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r1/stage-2-grader.json`): passed=False
