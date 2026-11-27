# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T07:51:25Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 148.43
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/corporate.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/holds_pricing.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 2 (multi-room group/corporate bookings without duplicating pricing/overlap logic or introducing circular imports):
- In `src/pricing.ts`: export `applyDiscountAndTax(grossSubtotalCents, discountBps, taxBps)` returning `{ subtotalCents, discountCents, taxCents, totalCents }` with exact integer half-up rounding (`discountCents = roundHalfUpDiv(grossSubtotalCents * discountBps, 10000)`, `subtotalCents = grossSubtotalCents - discountCents`, `taxCents = computeTaxCents(subtotalCents, taxBps)`, `totalCents = subtotalCents + taxCents`, validating integer bounds `0..10000` with `ValidationError`), and reuse it inside `calculateBookingPrice` with optional `discountBps = 0`.
- Add `src/corporate.ts` exporting `createGroupBooking(service, input)` (re-exported from `src/index.ts`, keeping module imports strictly acyclic — do NOT create circular imports between `bookings.ts` and `corporate.ts`!).
- `input` has `{ customerId, roomIds, startMinute, endMinute, discountBps, nowMinute? }`. Validate `roomIds.length >= 2`, no duplicate room IDs, valid `discountBps` (`0..10000`), and all rooms registered (`ValidationError`).
- Check slot conflicts across ALL requested rooms atomically BEFORE committing any booking (reusing `slotsOverlap` and `isBookingActiveAt` from `bookings.ts`, throwing `ConflictError` with zero partial bookings committed if any room conflicts).
- Price each room using the canonical `pricing.ts` helper, assign a shared `groupId` to every created booking, and return `{ groupId, bookings, subtotalCents, discountCents, taxCents, totalCents }`.
- Add strong `node:test` tests for multi-room pricing, atomic partial-conflict rollback, and validation errors, then run `run_checks.mjs`.

## Raw Model Output

Turn 2 is done: multi-room group bookings work, and `node run_checks.mjs` exits 0 with all 30 tests passing (19 from before, 11 new). There are no circular imports. The dependency order is `corporate.ts` → `bookings.ts` → `pricing.ts`/`config.ts` → `models.ts`, and `bookings.ts` never imports `corporate.ts`.

**What changed**
- **`src/pricing.ts`**
  - New `applyDiscountAndTax`, following your formula. It throws `ValidationError` for a negative or non-integer subtotal, and for discount or tax rates that aren't integers from 0 to 10000.
  - `calculateBookingPrice` now runs every price through it and takes an optional `discountBps` (default 0). The legacy deposit is now 25% of the discounted subtotal.
  - The 0–10000 check is a new exported `validateBps`, so `corporate.ts` uses the same check instead of its own copy.
- **`src/bookings.ts`**: three additions so `corporate.ts` doesn't need copies of existing logic.
  - `findActiveConflict` contains the overlap loop built on `slotsOverlap` and `isBookingActiveAt`. Single and group bookings both use it, so the loop exists in one place.
  - `validateSlotRequest` holds the customer, time-window and `nowMinute` checks that `createBooking` already did.
  - `commitBookingGroup(drafts)` assigns one `grp_…` group ID and a booking ID to each draft, then stores them all. It's needed because the service's booking list and ID counter are private.
- **`src/corporate.ts`**: `createGroupBooking` runs in this order:
  1. Validates everything: at least 2 rooms, no duplicates, valid discount, all rooms registered, valid time window.
  2. Checks every room for conflicts and throws `ConflictError` on the first one.
  3. Prices each room with `calculateBookingPrice`, rounding each room's discount separately.
  4. Stores all the bookings, which are confirmed, in one step.

  Nothing is stored before step 4, so a failure in any room leaves no partial bookings. Group totals are the sums of the per-room amounts.
- **`src/index.ts`**: re-exports `createGroupBooking`, `applyDiscountAndTax`, `validateBps` and the input/result types.

**One point to check:** you asked for `corporate.ts` to reuse `slotsOverlap` and `isBookingActiveAt`. It does, but through `findActiveConflict` rather than importing the two functions directly.

**Tests (`tests/corporate.test.ts`)**
- **Pricing:** discount rounding at exact halves, 0% and 100% discounts, out-of-range inputs, and a 2-room group checked by hand, including a 7498.5¢ amount rounding to 7499.
- **No partial bookings:** the conflicting room is listed last, so a version that stored rooms one at a time would leave the first two behind. The test checks the service is unchanged afterwards, and that holds block a group until they expire.
- **Validation:** 11 invalid-input cases, each leaving no bookings.
- **Imports:** a test reads the import lines in `src/` and fails if they form a cycle.

**Checking the tests:** I broke the code four ways to make sure the tests catch it, restoring it after each:

| Change | Tests failed |
|---|---|
| Group stores rooms one at a time | 5 |
| Discount rounded down instead of half-up | 1 |
| Duplicate-room check removed | 1 |
| Import from `bookings.ts` back to `corporate.ts` | 1 (after a fix) |

The import test first missed the cycle because it only recognised `import … from "…"` lines, not a plain `import "./corporate.ts"`. I fixed that, and it now catches both forms. The final run passes, and `src` and `tests` still contain no `enum`, `namespace` or constructor parameter properties.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=False
