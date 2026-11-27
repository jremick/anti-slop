# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T08:07:43Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 145.73
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

Turn 2 is in place, and `run_checks.mjs` exits 0 with all 29 tests passing.

**One deviation from your spec:** `corporate.ts` doesn't call `slotsOverlap`, `isBookingActiveAt` or the pricing helper itself. Its bookings go through a new all-or-nothing batch method, `BookingService.createBookings`, which does the conflict check and pricing with those same helpers. I did it this way because `corporate.ts` can't write into the service's private bookings map. The other options were a second conflict scan in `corporate.ts`, or a public method that saves already-priced bookings unchecked, which callers could misuse. If you want the conflict check written out in `corporate.ts` anyway, it's a small change.

**`src/pricing.ts`**
- **`applyDiscountAndTax(gross, discountBps, taxBps)`** works exactly as you specified: discount rounded half-up, then tax on the discounted subtotal. Out-of-range or non-integer inputs throw `ValidationError`.
- **`validateBps`** is a new shared check for rates in `0..10000`. `computeTaxCents` and `registerRoom` use it too.
- **`calculateBookingPrice`** now takes an optional `discountBps` (default 0) and gets its totals from `applyDiscountAndTax`. The legacy deposit is taken from the subtotal after the discount.

**`src/bookings.ts`**
- **`createBookings(inputs, { grouped? })`** checks, prices and conflict-tests every input before saving anything. It also catches overlapping slots on the same room within one batch. If any input conflicts, it throws a single `ConflictError` listing all the conflicts and saves nothing. With `grouped: true`, every booking gets the same new `grp_…` id.
- **`createBooking`** now just runs a batch of one, so single and group bookings share one code path.
- `CreateBookingInput` gains an optional `discountBps`.

**`src/corporate.ts` (new)**
- **`createGroupBooking(service, input)`** checks that there are at least two rooms, no duplicates, a valid `discountBps`, and that every room is registered. It then creates the bookings through `createBookings` with `grouped: true` and returns `{ groupId, bookings, subtotalCents, discountCents, taxCents, totalCents }`, with the totals added up across rooms.
- No imports go in a circle: `corporate.ts` imports from `bookings.ts`, `pricing.ts` and `models.ts`, and only `index.ts` imports `corporate.ts`. A test reads the files in `src/` and fails if any cycle appears.

**`tests/turn2.test.ts`** covers:
- **Pricing:** checked against hand-worked figures with exact halves, such as a 562.5¢ discount rounding to 563. Across three rooms the totals are subtotal 21037, discount 3713, tax 1371, total 22408.
- **All-or-nothing conflicts:** if one room is taken, the free rooms end up with no bookings and stay bookable afterwards. An active hold blocks a group booking, while an expired hold or a back-to-back slot doesn't.
- **Overlaps within one batch** are rejected.
- **Bad input:** 11 invalid group inputs each throw `ValidationError` and save nothing.

The discount is rounded per room and then added up, so a group total can differ by a cent from rounding one discount on the combined subtotal. That follows your instruction to price each room separately.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2/stage-2-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2/stage-2-grader.json`): passed=True
