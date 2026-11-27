# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T07:59:37Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 112.37
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/corporate.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn1.test.ts']
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

Turn 2 is in, and `node run_checks.mjs` exits 0 with all 39 tests passing (25 from before plus 14 new ones in `tests/corporate.test.ts`).

**Pricing (`src/pricing.ts`)**
- `applyDiscountAndTax(gross, discountBps, taxBps)` works exactly as you specified and throws `ValidationError` for any value outside its range.
- `calculateBookingPrice` now takes an optional `discountBps` (default 0) and uses `applyDiscountAndTax` for its discount and tax.
- I added `validateBps` for the 0..10000 check so it's written once.
- **Behaviour change:** the legacy deposit is now 25% of the discounted subtotal rather than the full price. This changes nothing when there's no discount.

**Group bookings (`src/corporate.ts`)**
`createGroupBooking(service, input)` runs in three steps:
1. **Validate:** all the checks you listed plus the customer, time window and `nowMinute`. Errors are `ValidationError`.
2. **Check every room for conflicts** using `slotsOverlap` and `isBookingActiveAt` from `bookings.ts`. A conflict in any room throws `ConflictError`, and the error names the existing booking.
3. **Price and save:** each room is priced with `calculateBookingPrice` and the discount. The group id is allocated only after pricing succeeds, so a failed request doesn't use one up. All bookings are saved together, share the `groupId`, and are returned in the order of `roomIds`. The group totals are the sums of the per-room amounts.

**No circular imports:** `corporate.ts` imports from `bookings.ts`, which imports from `pricing.ts`, and `bookings.ts` never imports `corporate.ts`. To let the group code save bookings without reaching into the service's private data, I added three things to `bookings.ts`:
- `BookingService.commitBookings(drafts)` checks every room is registered before saving anything, then saves all the drafts at once.
- `BookingService.allocateGroupId()` hands out group ids.
- `validateBookingWindow` holds the customer and time-window checks, now shared by `createBooking` and `createGroupBooking`.

These are re-exported from `src/index.ts` with `createGroupBooking` and its types.

**Tests** cover:
- the discount maths on exact and tie values, and its invariants over a grid of inputs
- a three-room group priced to the cent
- a single room's price passed through unchanged when the discount is 0
- conflicts in the first or the last room, each leaving zero bookings saved
- holds that are still active versus expired
- 13 kinds of invalid input
- a scan of the `src/` imports that fails if there's a cycle or if `bookings.ts` imports `corporate.ts`

One test had a misplaced parenthesis, so it passed without checking the error type. I fixed it and it still passes.

`commitBookings` doesn't check for conflicts itself; it relies on the caller (today only `createGroupBooking`) to do that first. I kept it that way so the conflict check isn't written twice. If you'd rather it be safe to call directly, it can re-check before saving.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1/stage-2-grader.json`): passed=False
