# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T08:22:43Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 169.04
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

Turn 2 is done, and `node run_checks.mjs` exits 0 with 33 tests passing (21 from before plus 12 new ones in `tests/turn2.test.ts`).

**Pricing (`src/pricing.ts`)**
- `applyDiscountAndTax(gross, discountBps, taxBps)` uses the formulas you gave. It throws `ValidationError` for a negative or non-integer gross amount, or a discount or tax rate that isn't a whole number from 0 to 10000.
- That range check is a new exported helper, `validateBps`.
- `calculateBookingPrice` now takes an optional `discountBps` (default 0) and runs it through `applyDiscountAndTax`. With no discount, prices are the same as before.

**Group bookings (`src/corporate.ts`, exported from `src/index.ts`)**
`createGroupBooking(service, input)` works in this order:
1. It validates the customer, times and `nowMinute` (using the same checks as `createBooking`), then the discount, at least 2 rooms, no duplicate room IDs, and that every room is registered.
2. It checks every requested room for conflicts using `slotsOverlap` and `isBookingActiveAt`. If any room conflicts it throws one `ConflictError` naming all the conflicting rooms and bookings, and books nothing.
3. It prices every room before booking any of them, so a pricing error can't stop it halfway.
4. It creates one booking per room through `service.createBooking`, all with the same `groupId` (`grp_…`). The returned totals are summed from those bookings.

**Other changes**
- **Imports:** `corporate.ts` imports `bookings.ts`, `pricing.ts` and `models.ts`; nothing except `index.ts` imports `corporate.ts`. A test reads the import statements in `src/` and fails on any import loop or if `bookings.ts` imports `corporate.ts`.
- **`bookings.ts`:** the customer/time checks moved into an exported `validateSlotRequest` so both modules share them, and I added a public `nextGroupId()`.
- **`createBooking`:** it now accepts optional `discountBps` and `groupId`. That way each group booking is priced and saved by the same code as a single booking.

**Decisions you may want to revisit**
- **No undo:** if a room fails partway through step 4, the rooms already booked are not reversed. The design relies on steps 1–3 catching every error `createBooking` can throw. That holds today, but a new check added only to `createBooking` would weaken it.
- **Legacy deposit with a discount:** the 25% deposit is now worked out on the discounted subtotal. Nothing currently combines a discount with legacy deposit mode, so no result changes today.
- **Group bookings are always confirmed.** There's no hold option.
- **Duplicate room IDs** are matched exactly, so `"r1"` and `" r1"` count as different (the second would then fail as an unknown room).

**Tests**
- **Group pricing:** worked out by hand for three rooms at 12.5% off over 90 minutes, including rounding (1501.5 → 1502, then a discount of 187.75 → 188). Group totals are subtotal 22314, discount 3188, tax 1191, total 23505.
- **Atomic conflicts:** only the last requested room is busy, so code that books rooms one at a time and stops on the first conflict would leave the first two booked. The test checks that nothing is stored.
- **Holds and back-to-back slots:** an active hold blocks the group and an expired one doesn't; back-to-back slots are allowed.
- **Validation:** 12 kinds of invalid input are each rejected with nothing booked, and a validation error is raised before a conflict error.

**Checking the tests:** I temporarily broke the code three ways, one at a time: removed the conflict check across all rooms, rounded discounts down instead of half-up, and made `bookings.ts` import `corporate.ts`. The suite failed each time; for the first, the two conflict tests are the ones that failed. The original files were restored, the suite passes again, and the files match the copies saved before the experiment.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=True
