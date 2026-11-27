# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T08:31:16Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 134.42
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/group_bookings.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/holds_conflicts_pricing.test.ts']
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

Turn 2 is implemented, and `node run_checks.mjs` exits 0 with all 33 tests passing (21 from before plus 12 new). There are no circular imports: `corporate.ts` imports from `bookings.ts`, `pricing.ts` and `models.ts`, none of which import it back. A test checks this by reading the import statements in `src/`.

**One change from your spec:** `corporate.ts` doesn't call `slotsOverlap` / `isBookingActiveAt` itself. The service's list of bookings is private, so letting `corporate.ts` save bookings directly would have meant a second copy of the validate → price → conflict-check → save logic. Instead:
- **New `BookingService.createBookingBatch(inputs, { grouped })`** in `bookings.ts` checks and prices every input, then checks every slot against active bookings (using `slotsOverlap` and `isBookingActiveAt`) and against the rest of the batch. Only after all that passes does it save. Any error leaves the service unchanged.
- **`createBooking`** is now just a batch of one, so single and group bookings share one validation, pricing and conflict path.

If you'd rather `corporate.ts` call the overlap helpers directly, the service would need some public way to save already-checked bookings. That's doable, but it duplicates the conflict loop.

**`src/pricing.ts`**
- `applyDiscountAndTax` follows your formulas.
- A new `validateBps` checks that a rate is a whole number from 0 to 10000. Tax, discount and room registration all use it now, replacing three copies of the same check.
- `calculateBookingPrice` takes an optional `discountBps` (default 0) and uses `applyDiscountAndTax`. The legacy deposit is now 25% of the subtotal after the discount; that's my reading, since you didn't specify.
- `CreateBookingInput` gains an optional `discountBps`, so single bookings can be discounted too.

**`src/corporate.ts`**
- `createGroupBooking` checks: at least 2 rooms, no duplicate rooms, a valid `discountBps`, and every room registered. It then calls the batch method with `grouped: true`.
- Each room is priced and rounded on its own because tax rates differ per room. The group totals are the sums of the per-room amounts.

**`src/index.ts`** now also exports `applyDiscountAndTax`, `validateBps`, `createGroupBooking` and the new types.

**Tests** (`tests/group_bookings.test.ts`):
- **Pricing:** `applyDiscountAndTax` at exact halves and at 0% and 100% discount. A three-room group with different rates and tax rates has every per-room and group amount worked out by hand; for example, the group total is 28103¢.
- **Group IDs:** all bookings in a group share one `groupId`, and different groups get different ones. Plain bookings have no `groupId`.
- **All-or-nothing:** a clash in the middle room or the last room leaves zero new bookings saved, and the other rooms can still be booked afterwards. Holds block a group until their exact expiry minute.
- **Validation:** 13 invalid inputs each throw `ValidationError` and save nothing.
- **Import cycles:** the import-graph check described above.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3/stage-2-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3/stage-2-grader.json`): passed=True
