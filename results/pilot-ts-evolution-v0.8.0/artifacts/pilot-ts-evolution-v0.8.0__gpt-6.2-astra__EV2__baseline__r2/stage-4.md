# pilot-ts-evolution-v0.8.0__gpt-6.2-astra__EV2__baseline__r2 — Stage 4/4

- Timestamp UTC: 2026-11-27T08:09:40Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: baseline
- Elapsed seconds: 92.12
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/config.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts', 'benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/cancellation.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/corporate.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/notifications.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn1.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 4 (complete removal of `legacyDepositMode` / `calculateLegacyDeposit` and atomic fail-closed `notifyHook`):
- Completely remove `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode`, and `depositCents` from `src/models.ts`, `src/pricing.ts`, `src/bookings.ts`, `src/index.ts`, and `tests/` (do NOT leave dead branches, legacy shims, or speculative single-implementation `*Factory`/`*Wrapper` abstractions).
- Add optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions`, where `BookingNotification` has `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }`.
- Invoke `notifyHook` on every newly created booking (including every room booking created via `createGroupBooking`, with `amountCents: booking.totalCents`) and on every cancellation (`event: 'booking_cancelled'`, `amountCents: refundCents`). Enforce fail-closed atomicity: if `notifyHook` throws, propagate the error AND roll back so zero new bookings (including partial group bookings) or cancellation status changes are persisted.
- Update `tests/` to verify legacy deposit exports are gone and `notifyHook` emits exact events and rolls back atomically on failure, then run `run_checks.mjs`.

## Raw Model Output

Removed all four legacy deposit identifiers from source and tests. `notifyHook` now receives each new booking’s total, including each room in a group, and the refund amount on cancellation.

Booking changes commit only after all required hooks succeed. A thrown hook error propagates unchanged, leaves the entire group unbooked, and preserves the original reservation on failed cancellation. The service also rejects nested notification dispatch from inside a hook.

`node benchmarks/sources/ev2_ts_bookings/run_checks.mjs` exited 0. **All 21 tests passed**, including exact event payloads, failure on the second group notification, and successful retries.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__gpt-6.2-astra__EV2__baseline__r2/stage-4-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__gpt-6.2-astra__EV2__baseline__r2/stage-4-grader.json`): passed=True
