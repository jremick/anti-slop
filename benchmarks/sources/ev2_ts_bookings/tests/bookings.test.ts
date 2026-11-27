import test from "node:test";
import assert from "node:assert/strict";
import {
  BookingService,
  ValidationError,
  calculateLegacyDeposit,
} from "../src/index.ts";

test("baseline whole-hour booking computes exact subtotal and tax", () => {
  const svc = new BookingService({ env: {} });
  svc.registerRoom({
    roomId: "conf_a",
    name: "Conference A",
    hourlyRateCents: 10000,
    taxBps: 825,
  });

  const booking = svc.createBooking({
    roomId: "conf_a",
    customerId: "cust_1",
    startMinute: 60,
    endMinute: 180,
  });

  assert.equal(booking.status, "confirmed");
  assert.equal(booking.subtotalCents, 20000);
  assert.equal(booking.taxCents, 1650);
  assert.equal(booking.totalCents, 21650);
  assert.equal(booking.depositCents, 0);
  assert.equal(svc.listRoomBookings("conf_a").length, 1);
});

test("baseline legacy deposit mode calculates 25 percent deposit", () => {
  const svc = new BookingService({ env: {} });
  svc.registerRoom({
    roomId: "conf_b",
    name: "Conference B",
    hourlyRateCents: 4000,
    taxBps: 0,
  });

  const booking = svc.createBooking({
    roomId: "conf_b",
    customerId: "cust_2",
    startMinute: 0,
    endMinute: 60,
    legacyDepositMode: true,
  });

  assert.equal(calculateLegacyDeposit(4000), 1000);
  assert.equal(booking.depositCents, 1000);
});

test("baseline rejects invalid room or inverted time range", () => {
  const svc = new BookingService({ env: {} });
  svc.registerRoom({
    roomId: "conf_c",
    name: "Conference C",
    hourlyRateCents: 5000,
    taxBps: 500,
  });

  assert.throws(
    () =>
      svc.createBooking({
        roomId: "missing",
        customerId: "cust_1",
        startMinute: 0,
        endMinute: 60,
      }),
    ValidationError,
  );
  assert.throws(
    () =>
      svc.createBooking({
        roomId: "conf_c",
        customerId: "cust_1",
        startMinute: 120,
        endMinute: 60,
      }),
    ValidationError,
  );
});
