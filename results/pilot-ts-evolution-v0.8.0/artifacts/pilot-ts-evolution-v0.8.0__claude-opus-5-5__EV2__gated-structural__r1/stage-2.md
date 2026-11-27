# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T07:43:18Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 136.82
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn1.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn2.test.ts']
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

Turn 2 is in: you can now book the same slot in several rooms at once, and either every room is booked or none is. `run_checks.mjs` passes all 33 tests and exits 0. There's no `tsc` installed here, so the code was only checked by running it under Node, not type-checked.

**Imports run one way only:** `corporate.ts` → `bookings.ts` → `pricing.ts` → `models.ts`. Nothing imports `corporate.ts` except `index.ts`, and a new test reads the import lines in `src/` and fails if any cycle appears.

**`src/pricing.ts`**
- `applyDiscountAndTax(gross, discountBps, taxBps)` works exactly as you specified. The returned `subtotalCents` is the amount after the discount.
- New `validateBps` checks that a rate is a whole number from 0 to 10000. `computeTaxCents` and `registerRoom` now use it too, instead of repeating the check.
- `calculateBookingPrice` takes an optional `discountBps` (default 0) and calls `applyDiscountAndTax`. With legacy deposit mode, the 25% deposit is taken from the discounted subtotal. You didn't specify this, so check it's what you want.

**`src/bookings.ts`**
- **One place for conflict checks:** `findConflictingBooking` uses `slotsOverlap` and `isBookingActiveAt` to find the first active booking that overlaps a slot. `createBooking` and group bookings both go through it, so the overlap logic isn't copied.
- **One place for basic checks:** `validateBookingRequest` checks the customer ID and the time slot, and both booking paths use it.
- **Atomic saving:** `BookingService.commitBookings(drafts, nowMinute)` checks every booking first, including overlaps within the same batch. It stores them only if all pass, so a conflict leaves nothing saved. `createBooking` now saves through this method as well.
- `BookingService.allocateGroupId()` hands out `grp_NNNN` IDs from the same counter as booking IDs.

**Things to be aware of**
- **`commitBookings` is public:** TypeScript has no way to share it only with `corporate.ts`. It trusts the prices it is given, though it still rejects unknown rooms and conflicts. Anyone can call it with any prices.
- **Booking IDs can skip numbers:** a group ID is reserved before the conflict check, so a group that fails on a conflict still uses up one number.

**`src/corporate.ts`**
- `createGroupBooking(service, input)` runs its checks in this order: customer and slot, at least 2 rooms, no duplicate rooms, discount from 0 to 10000, `nowMinute`, and all rooms registered.
- It then prices each room with `calculateBookingPrice` at that room's own rate and tax, plus the shared discount. It saves everything through `commitBookings` and returns the group ID, the bookings, and totals summed across rooms. All the bookings are confirmed and share the same `groupId`.

**Tests (`tests/turn2.test.ts`, 12 new)**
- **Pricing:** discount and tax with exact half-up rounding and the 0/10000 limits, plus a group whose rooms have different rates and taxes, checked against hand-calculated cents.
- **All-or-nothing:**
  - When the conflict is on the last room of three, nothing is saved and the error names the booking that blocked it.
  - An active hold blocks a group, but an expired one doesn't.
- **Invalid input:** 13 bad inputs each throw `ValidationError` and save nothing.
- **Imports:** the cycle check described above.

`index.ts` exports all the new functions and types.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1/stage-2-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1/stage-2-grader.json`): passed=True
