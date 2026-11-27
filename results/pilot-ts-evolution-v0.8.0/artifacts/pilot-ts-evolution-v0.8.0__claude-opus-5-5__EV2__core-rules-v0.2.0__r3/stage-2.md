# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T08:38:17Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 132.73
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

Turn 2 is implemented, and `run_checks.mjs` exits 0 with 26 tests passing (17 from before and 9 new). The imports stay one-way: `corporate.ts` imports `bookings.ts` and never the reverse. A new test checks every file in `src/` for import cycles, and I confirmed it fails when I temporarily added an import from `bookings.ts` to `corporate.ts`.

**Pricing (`src/pricing.ts`)**
- Added `applyDiscountAndTax` exactly as you specified, plus a shared `validateBps` that checks discount and tax rates are whole numbers from 0 to 10000.
- `calculateBookingPrice` now accepts an optional `discountBps` (default 0) and uses `applyDiscountAndTax`. With no discount the results are unchanged.

**Bookings (`src/bookings.ts`)**
To let group bookings share the existing conflict and storage code without a circular import, I split part of `createBooking` out into:
- **`validateBookingWindow`**: the customer and start/end checks, now shared by single and group bookings.
- **`BookingService.findActiveConflict`**: now the only place that loops over bookings with `slotsOverlap` and `isBookingActiveAt`.
- **`BookingService.commitBookings(drafts, nowMinute)`**: checks every draft for conflicts, including against other drafts in the same batch, before storing any of them. If one fails, nothing is stored. `createBooking` now goes through it too.

**Group bookings (`src/corporate.ts`)**
`createGroupBooking` checks its inputs first: at least 2 rooms, no duplicate rooms, a valid `discountBps`, a valid time window and registered rooms. It then prices each room with `calculateBookingPrice`, gives every booking the same `groupId`, and stores them all at once through `commitBookings`. The group totals are the sums of the per-room amounts.

**Choices that differ from a literal reading of the spec**
- **Conflict check location:** `corporate.ts` doesn't import `slotsOverlap` or `isBookingActiveAt` directly. It reuses them through `commitBookings`, so the conflict loop and the all-or-nothing rule live in one place rather than being repeated in `corporate.ts`.
- **Rounding per room:** each room's discount and tax are rounded separately and then added up, as you asked. Applying the discount to the combined subtotal could differ by a cent.
- **Legacy deposit:** it is now 25% of the discounted subtotal. This only matters if a discount and legacy deposit mode are used together, which no current code path does.
- **Group IDs:** they come from one counter shared by the whole program (`grp_0001`, …), not one counter per `BookingService`.

**New tests (`tests/corporate.test.ts`)**
- Exact discount and tax values, including half-cent cases and rejected out-of-range rates.
- A three-room group with every per-room amount and group total checked by hand.
- A conflict on one room leaves zero new bookings, and the other rooms can still be booked afterwards.
- Holds that are still live block a group booking; expired holds and back-to-back slots don't.
- Eleven kinds of invalid input are rejected, with nothing stored.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r3/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r3/stage-2-grader.json`): passed=True
