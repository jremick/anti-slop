"""Stdlib-only tests for EV2 4-turn TypeScript evolution benchmark and mechanical grader."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.graders import grade_ev2  # noqa: E402


FIXTURE_DIR = REPO_ROOT / "benchmarks" / "sources" / "ev2_ts_bookings"


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark", REPO_ROOT / "scripts" / "benchmark.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _node_supports_native_ts() -> bool:
    try:
        proc = subprocess.run(["node", "--version"], capture_output=True, text=True, check=False)
    except OSError:
        return False
    if proc.returncode != 0:
        return False
    parts = proc.stdout.strip().lstrip("v").split(".")
    try:
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0) >= (22, 6)
    except ValueError:
        return False


def _check_map(report: dict) -> dict[str, dict]:
    return {c["id"]: c for c in report["checks"]}


CLEAN_MODELS_TS = """export class BookingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BookingError";
  }
}

export class ValidationError extends BookingError {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

export class ConflictError extends BookingError {
  constructor(message: string) {
    super(message);
    this.name = "ConflictError";
  }
}

export class ConfigError extends BookingError {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

export type BookingStatus = "confirmed" | "held" | "cancelled";

export interface Room {
  readonly roomId: string;
  readonly name: string;
  readonly hourlyRateCents: number;
  readonly taxBps: number;
}

export interface PriceBreakdown {
  readonly subtotalCents: number;
  readonly discountCents: number;
  readonly taxCents: number;
  readonly totalCents: number;
}

export interface Booking {
  readonly bookingId: string;
  readonly roomId: string;
  readonly customerId: string;
  readonly startMinute: number;
  readonly endMinute: number;
  readonly status: BookingStatus;
  readonly subtotalCents: number;
  readonly discountCents: number;
  readonly taxCents: number;
  readonly totalCents: number;
  readonly expiresAt?: number;
  readonly groupId?: string;
}

export interface CreateBookingInput {
  readonly roomId: string;
  readonly customerId: string;
  readonly startMinute: number;
  readonly endMinute: number;
  readonly nowMinute?: number;
  readonly holdMinutes?: number;
  readonly discountBps?: number;
  readonly groupId?: string;
}

export interface BookingNotification {
  readonly event: "booking_created" | "booking_cancelled";
  readonly bookingId: string;
  readonly roomId: string;
  readonly customerId: string;
  readonly amountCents: number;
}

export interface CancellationResult {
  readonly booking: Booking;
  readonly feeBps: number;
  readonly feeCents: number;
  readonly refundCents: number;
}
"""

CLEAN_CONFIG_TS = """import { ConfigError } from "./models.ts";

export interface BookingConfig {
  readonly maxHoldMinutes: number;
}

export interface CancellationFeeConfig {
  readonly cutoffMinutes: number;
  readonly earlyFeeBps: number;
  readonly lateFeeBps: number;
}

export const DEFAULT_MAX_HOLD_MINUTES = 60;

export function loadBookingConfig(
  env: Record<string, string | undefined> = process.env,
): BookingConfig {
  const rawHold = env.BOOKING_MAX_HOLD_MINUTES;
  if (rawHold === undefined || rawHold.trim() === "") {
    return { maxHoldMinutes: DEFAULT_MAX_HOLD_MINUTES };
  }
  const parsed = Number(rawHold);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new ConfigError("BOOKING_MAX_HOLD_MINUTES must be a positive integer");
  }
  return { maxHoldMinutes: parsed };
}

function requireBps(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 10000) {
    throw new ConfigError(`${label} must be an integer between 0 and 10000`);
  }
  return value;
}

export function loadCancellationFeeConfig(
  env: Record<string, string | undefined> = process.env,
): CancellationFeeConfig {
  const raw = env.BOOKING_CANCEL_FEE_TIERS_JSON;
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new ConfigError("BOOKING_CANCEL_FEE_TIERS_JSON is required");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new ConfigError(`Invalid BOOKING_CANCEL_FEE_TIERS_JSON: ${String(err)}`);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new ConfigError("BOOKING_CANCEL_FEE_TIERS_JSON must be a JSON object");
  }
  const rec = parsed as Record<string, unknown>;
  const cutoffMinutes = rec.cutoffMinutes;
  if (typeof cutoffMinutes !== "number" || !Number.isInteger(cutoffMinutes) || cutoffMinutes < 0) {
    throw new ConfigError("cutoffMinutes must be a non-negative integer");
  }
  return {
    cutoffMinutes,
    earlyFeeBps: requireBps(rec.earlyFeeBps, "earlyFeeBps"),
    lateFeeBps: requireBps(rec.lateFeeBps, "lateFeeBps"),
  };
}

export function selectCancellationFeeBps(
  minutesBeforeStart: number,
  cfg: CancellationFeeConfig,
): number {
  if (minutesBeforeStart >= cfg.cutoffMinutes) {
    return cfg.earlyFeeBps;
  }
  return cfg.lateFeeBps;
}
"""

CLEAN_PRICING_TS = """import { ValidationError } from "./models.ts";
import type { PriceBreakdown, Room } from "./models.ts";

export function validateNonNegativeInt(value: number, fieldName: string): number {
  if (!Number.isInteger(value) || value < 0) {
    throw new ValidationError(`${fieldName} must be a non-negative integer`);
  }
  return value;
}

export function validatePositiveInt(value: number, fieldName: string): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new ValidationError(`${fieldName} must be a positive integer`);
  }
  return value;
}

export function roundHalfUpDiv(numerator: number, denominator: number): number {
  validateNonNegativeInt(numerator, "numerator");
  validatePositiveInt(denominator, "denominator");
  return Math.floor((numerator * 2 + denominator) / (2 * denominator));
}

export function computeTaxCents(taxableCents: number, taxBps: number): number {
  validateNonNegativeInt(taxableCents, "taxableCents");
  validateNonNegativeInt(taxBps, "taxBps");
  if (taxBps > 10000) {
    throw new ValidationError("taxBps cannot exceed 10000");
  }
  return roundHalfUpDiv(taxableCents * taxBps, 10000);
}

export function applyDiscountAndTax(
  grossSubtotalCents: number,
  discountBps: number,
  taxBps: number,
): PriceBreakdown {
  validateNonNegativeInt(grossSubtotalCents, "grossSubtotalCents");
  validateNonNegativeInt(discountBps, "discountBps");
  if (discountBps > 10000) {
    throw new ValidationError("discountBps cannot exceed 10000");
  }
  const discountCents = roundHalfUpDiv(grossSubtotalCents * discountBps, 10000);
  const subtotalCents = grossSubtotalCents - discountCents;
  const taxCents = computeTaxCents(subtotalCents, taxBps);
  return {
    subtotalCents,
    discountCents,
    taxCents,
    totalCents: subtotalCents + taxCents,
  };
}

export function calculateBookingPrice(
  room: Room,
  durationMinutes: number,
  options?: { readonly discountBps?: number },
): PriceBreakdown {
  validatePositiveInt(room.hourlyRateCents, "hourlyRateCents");
  validatePositiveInt(durationMinutes, "durationMinutes");
  const grossSubtotalCents = roundHalfUpDiv(room.hourlyRateCents * durationMinutes, 60);
  const discountBps = options?.discountBps ?? 0;
  return applyDiscountAndTax(grossSubtotalCents, discountBps, room.taxBps);
}

export function computeCancellationRefund(
  totalCents: number,
  feeBps: number,
): { readonly feeCents: number; readonly refundCents: number } {
  validateNonNegativeInt(totalCents, "totalCents");
  validateNonNegativeInt(feeBps, "feeBps");
  if (feeBps > 10000) {
    throw new ValidationError("feeBps cannot exceed 10000");
  }
  const feeCents = roundHalfUpDiv(totalCents * feeBps, 10000);
  return { feeCents, refundCents: totalCents - feeCents };
}
"""

CLEAN_BOOKINGS_TS = """import {
  loadBookingConfig,
  loadCancellationFeeConfig,
  selectCancellationFeeBps,
} from "./config.ts";
import type { BookingConfig } from "./config.ts";
import { ConflictError, ValidationError } from "./models.ts";
import type {
  Booking,
  BookingNotification,
  CancellationResult,
  CreateBookingInput,
  Room,
} from "./models.ts";
import {
  calculateBookingPrice,
  computeCancellationRefund,
  validateNonNegativeInt,
  validatePositiveInt,
} from "./pricing.ts";

export interface BookingServiceOptions {
  readonly env?: Record<string, string | undefined>;
  readonly notifyHook?: (event: BookingNotification) => void;
}

export function slotsOverlap(
  startA: number,
  endA: number,
  startB: number,
  endB: number,
): boolean {
  return startA < endB && startB < endA;
}

export function isBookingActiveAt(booking: Booking, nowMinute: number): boolean {
  if (booking.status === "confirmed") {
    return true;
  }
  if (booking.status === "held" && booking.expiresAt !== undefined) {
    return nowMinute < booking.expiresAt;
  }
  return false;
}

export function validateBookingWindow(
  customerId: string,
  startMinute: number,
  endMinute: number,
  nowMinute: number,
): string {
  if (typeof customerId !== "string" || customerId.trim() === "") {
    throw new ValidationError("customerId must be a non-empty string");
  }
  validateNonNegativeInt(nowMinute, "nowMinute");
  validateNonNegativeInt(startMinute, "startMinute");
  validatePositiveInt(endMinute, "endMinute");
  if (endMinute <= startMinute) {
    throw new ValidationError("endMinute must be strictly greater than startMinute");
  }
  return customerId.trim();
}

export class BookingService {
  readonly config: BookingConfig;
  private readonly env: Record<string, string | undefined>;
  private readonly notifyHook?: (event: BookingNotification) => void;
  private readonly rooms: Map<string, Room> = new Map();
  private readonly bookings: Map<string, Booking> = new Map();
  private seq = 0;

  constructor(options: BookingServiceOptions = {}) {
    this.env = options.env ?? process.env;
    this.config = loadBookingConfig(this.env);
    this.notifyHook = options.notifyHook;
  }

  allocateId(prefix: string): string {
    this.seq += 1;
    return `${prefix}_${String(this.seq).padStart(4, "0")}`;
  }

  private emitNotification(event: BookingNotification): void {
    if (this.notifyHook !== undefined) {
      this.notifyHook(event);
    }
  }

  registerRoom(room: Room): void {
    if (typeof room.roomId !== "string" || room.roomId.trim() === "") {
      throw new ValidationError("roomId must be a non-empty string");
    }
    if (typeof room.name !== "string" || room.name.trim() === "") {
      throw new ValidationError("name must be a non-empty string");
    }
    validatePositiveInt(room.hourlyRateCents, "hourlyRateCents");
    validateNonNegativeInt(room.taxBps, "taxBps");
    if (room.taxBps > 10000) {
      throw new ValidationError("taxBps cannot exceed 10000");
    }
    this.rooms.set(room.roomId, room);
  }

  getRoom(roomId: string): Room {
    const room = this.rooms.get(roomId);
    if (room === undefined) {
      throw new ValidationError(`Unknown roomId: ${roomId}`);
    }
    return room;
  }

  getBooking(bookingId: string): Booking {
    const booking = this.bookings.get(bookingId);
    if (booking === undefined) {
      throw new ValidationError(`Unknown bookingId: ${bookingId}`);
    }
    return booking;
  }

  listRoomBookings(roomId: string): Booking[] {
    this.getRoom(roomId);
    const matches: Booking[] = [];
    for (const booking of this.bookings.values()) {
      if (booking.roomId === roomId) {
        matches.push(booking);
      }
    }
    return matches;
  }

  assertSlotAvailable(roomId: string, startMinute: number, endMinute: number, nowMinute: number): void {
    for (const existing of this.listRoomBookings(roomId)) {
      if (isBookingActiveAt(existing, nowMinute) && slotsOverlap(existing.startMinute, existing.endMinute, startMinute, endMinute)) {
        throw new ConflictError(`Room ${roomId} is already booked for this slot`);
      }
    }
  }

  commitBookingsAtomic(pending: readonly Booking[]): void {
    for (const booking of pending) {
      this.emitNotification({
        event: "booking_created",
        bookingId: booking.bookingId,
        roomId: booking.roomId,
        customerId: booking.customerId,
        amountCents: booking.totalCents,
      });
    }
    for (const booking of pending) {
      this.bookings.set(booking.bookingId, booking);
    }
  }

  createBooking(input: CreateBookingInput): Booking {
    const nowMinute = input.nowMinute ?? 0;
    const customer = validateBookingWindow(input.customerId, input.startMinute, input.endMinute, nowMinute);
    const room = this.getRoom(input.roomId);
    let expiresAt: number | undefined;
    if (input.holdMinutes !== undefined) {
      validatePositiveInt(input.holdMinutes, "holdMinutes");
      if (input.holdMinutes > this.config.maxHoldMinutes) {
        throw new ValidationError("holdMinutes exceeds maxHoldMinutes");
      }
      expiresAt = nowMinute + input.holdMinutes;
    }
    this.assertSlotAvailable(room.roomId, input.startMinute, input.endMinute, nowMinute);
    const price = calculateBookingPrice(room, input.endMinute - input.startMinute, {
      discountBps: input.discountBps ?? 0,
    });
    const booking: Booking = {
      bookingId: this.allocateId("bkg"),
      roomId: room.roomId,
      customerId: customer,
      startMinute: input.startMinute,
      endMinute: input.endMinute,
      status: expiresAt !== undefined ? "held" : "confirmed",
      subtotalCents: price.subtotalCents,
      discountCents: price.discountCents,
      taxCents: price.taxCents,
      totalCents: price.totalCents,
      ...(expiresAt !== undefined ? { expiresAt } : {}),
      ...(input.groupId !== undefined ? { groupId: input.groupId } : {}),
    };
    this.commitBookingsAtomic([booking]);
    return booking;
  }

  confirmHold(bookingId: string, nowMinute: number): Booking {
    validateNonNegativeInt(nowMinute, "nowMinute");
    const existing = this.getBooking(bookingId);
    if (existing.status !== "held" || existing.expiresAt === undefined) {
      throw new ValidationError("Booking is not an active hold");
    }
    if (nowMinute >= existing.expiresAt) {
      throw new ValidationError("Hold has already expired");
    }
    const updated: Booking = {
      bookingId: existing.bookingId,
      roomId: existing.roomId,
      customerId: existing.customerId,
      startMinute: existing.startMinute,
      endMinute: existing.endMinute,
      status: "confirmed",
      subtotalCents: existing.subtotalCents,
      discountCents: existing.discountCents,
      taxCents: existing.taxCents,
      totalCents: existing.totalCents,
      ...(existing.groupId !== undefined ? { groupId: existing.groupId } : {}),
    };
    this.bookings.set(updated.bookingId, updated);
    return updated;
  }

  cancelBooking(bookingId: string, nowMinute: number): CancellationResult {
    validateNonNegativeInt(nowMinute, "nowMinute");
    const existing = this.getBooking(bookingId);
    if (existing.status === "cancelled") {
      throw new ValidationError("Booking is already cancelled");
    }
    if (nowMinute > existing.startMinute) {
      throw new ValidationError("Cannot cancel booking after startMinute");
    }
    const cfg = loadCancellationFeeConfig(this.env);
    const feeBps = selectCancellationFeeBps(existing.startMinute - nowMinute, cfg);
    const { feeCents, refundCents } = computeCancellationRefund(existing.totalCents, feeBps);
    const cancelled: Booking = { ...existing, status: "cancelled" };
    this.emitNotification({
      event: "booking_cancelled",
      bookingId: cancelled.bookingId,
      roomId: cancelled.roomId,
      customerId: cancelled.customerId,
      amountCents: refundCents,
    });
    this.bookings.set(cancelled.bookingId, cancelled);
    return { booking: cancelled, feeBps, feeCents, refundCents };
  }
}
"""

CLEAN_CORPORATE_TS = """import { BookingService, validateBookingWindow } from "./bookings.ts";
import { ValidationError } from "./models.ts";
import type { Booking } from "./models.ts";
import { calculateBookingPrice } from "./pricing.ts";

export interface GroupBookingInput {
  readonly customerId: string;
  readonly roomIds: readonly string[];
  readonly startMinute: number;
  readonly endMinute: number;
  readonly discountBps: number;
  readonly nowMinute?: number;
}

export interface GroupBookingResult {
  readonly groupId: string;
  readonly bookings: readonly Booking[];
  readonly subtotalCents: number;
  readonly discountCents: number;
  readonly taxCents: number;
  readonly totalCents: number;
}

export function createGroupBooking(
  service: BookingService,
  input: GroupBookingInput,
): GroupBookingResult {
  const nowMinute = input.nowMinute ?? 0;
  const customer = validateBookingWindow(input.customerId, input.startMinute, input.endMinute, nowMinute);
  if (!Array.isArray(input.roomIds) || input.roomIds.length < 2) {
    throw new ValidationError("Group booking requires at least 2 rooms");
  }
  if (new Set(input.roomIds).size !== input.roomIds.length) {
    throw new ValidationError("Duplicate roomIds are not allowed");
  }
  const rooms = input.roomIds.map((rid) => service.getRoom(rid));
  for (const room of rooms) {
    service.assertSlotAvailable(room.roomId, input.startMinute, input.endMinute, nowMinute);
  }
  const groupId = service.allocateId("grp");
  const duration = input.endMinute - input.startMinute;
  const pending: Booking[] = [];
  let subtotalCents = 0;
  let discountCents = 0;
  let taxCents = 0;
  let totalCents = 0;
  for (const room of rooms) {
    const price = calculateBookingPrice(room, duration, { discountBps: input.discountBps });
    pending.push({
      bookingId: service.allocateId("bkg"),
      roomId: room.roomId,
      customerId: customer,
      startMinute: input.startMinute,
      endMinute: input.endMinute,
      status: "confirmed",
      subtotalCents: price.subtotalCents,
      discountCents: price.discountCents,
      taxCents: price.taxCents,
      totalCents: price.totalCents,
      groupId,
    });
    subtotalCents += price.subtotalCents;
    discountCents += price.discountCents;
    taxCents += price.taxCents;
    totalCents += price.totalCents;
  }
  service.commitBookingsAtomic(pending);
  return { groupId, bookings: pending, subtotalCents, discountCents, taxCents, totalCents };
}
"""

CLEAN_INDEX_TS = """export {
  BookingError,
  ConfigError,
  ConflictError,
  ValidationError,
} from "./models.ts";
export type {
  Booking,
  BookingNotification,
  BookingStatus,
  CancellationResult,
  CreateBookingInput,
  PriceBreakdown,
  Room,
} from "./models.ts";
export {
  DEFAULT_MAX_HOLD_MINUTES,
  loadBookingConfig,
  loadCancellationFeeConfig,
  selectCancellationFeeBps,
} from "./config.ts";
export type { BookingConfig, CancellationFeeConfig } from "./config.ts";
export {
  applyDiscountAndTax,
  calculateBookingPrice,
  computeCancellationRefund,
  computeTaxCents,
  roundHalfUpDiv,
  validateNonNegativeInt,
  validatePositiveInt,
} from "./pricing.ts";
export {
  BookingService,
  isBookingActiveAt,
  slotsOverlap,
} from "./bookings.ts";
export type { BookingServiceOptions } from "./bookings.ts";
export { createGroupBooking } from "./corporate.ts";
export type { GroupBookingInput, GroupBookingResult } from "./corporate.ts";
"""

CLEAN_TESTS_TS = """import test from "node:test";
import assert from "node:assert/strict";
import * as api from "../src/index.ts";
import {
  BookingService,
  ConfigError,
  ConflictError,
  ValidationError,
  applyDiscountAndTax,
  calculateBookingPrice,
  computeCancellationRefund,
  computeTaxCents,
  createGroupBooking,
  isBookingActiveAt,
  loadBookingConfig,
  loadCancellationFeeConfig,
  roundHalfUpDiv,
  selectCancellationFeeBps,
  slotsOverlap,
} from "../src/index.ts";

const VALID_TIERS = JSON.stringify({ cutoffMinutes: 1440, earlyFeeBps: 1000, lateFeeBps: 5000 });

test("pricing helpers round half-up and validate bounds", () => {
  assert.equal(roundHalfUpDiv(3, 2), 2);
  assert.equal(roundHalfUpDiv(4, 2), 2);
  assert.equal(roundHalfUpDiv(5, 2), 3);
  assert.equal(roundHalfUpDiv(0, 5), 0);
  assert.throws(() => roundHalfUpDiv(-1, 2), ValidationError);
  assert.throws(() => roundHalfUpDiv(1, 0), ValidationError);
  assert.throws(() => roundHalfUpDiv(1.5, 2), ValidationError);

  assert.equal(computeTaxCents(1000, 825), 83);
  assert.equal(computeTaxCents(1000, 10000), 1000);
  assert.throws(() => computeTaxCents(-1, 100), ValidationError);
  assert.throws(() => computeTaxCents(100, 10001), ValidationError);

  const disc = applyDiscountAndTax(1005, 1000, 825);
  assert.deepEqual(disc, { subtotalCents: 904, discountCents: 101, taxCents: 75, totalCents: 979 });
  assert.throws(() => applyDiscountAndTax(100, 10001, 0), ValidationError);

  const room = { roomId: "r1", name: "R1", hourlyRateCents: 1001, taxBps: 825 };
  assert.deepEqual(calculateBookingPrice(room, 90), {
    subtotalCents: 1502,
    discountCents: 0,
    taxCents: 124,
    totalCents: 1626,
  });
  assert.deepEqual(computeCancellationRefund(1005, 1000), { feeCents: 101, refundCents: 904 });
  assert.throws(() => computeCancellationRefund(100, 10001), ValidationError);
});

test("config validation fails closed on missing or invalid env values", () => {
  assert.deepEqual(loadBookingConfig({}), { maxHoldMinutes: 60 });
  assert.deepEqual(loadBookingConfig({ BOOKING_MAX_HOLD_MINUTES: "30" }), { maxHoldMinutes: 30 });
  assert.throws(() => loadBookingConfig({ BOOKING_MAX_HOLD_MINUTES: "0" }), ConfigError);
  assert.throws(() => loadBookingConfig({ BOOKING_MAX_HOLD_MINUTES: "abc" }), ConfigError);

  const cfg = loadCancellationFeeConfig({ BOOKING_CANCEL_FEE_TIERS_JSON: VALID_TIERS });
  assert.deepEqual(cfg, { cutoffMinutes: 1440, earlyFeeBps: 1000, lateFeeBps: 5000 });
  assert.equal(selectCancellationFeeBps(1440, cfg), 1000);
  assert.equal(selectCancellationFeeBps(1439, cfg), 5000);

  assert.throws(() => loadCancellationFeeConfig({}), ConfigError);
  assert.throws(() => loadCancellationFeeConfig({ BOOKING_CANCEL_FEE_TIERS_JSON: "{" }), ConfigError);
  assert.throws(() => loadCancellationFeeConfig({ BOOKING_CANCEL_FEE_TIERS_JSON: "[]" }), ConfigError);
  assert.throws(
    () => loadCancellationFeeConfig({ BOOKING_CANCEL_FEE_TIERS_JSON: JSON.stringify({ cutoffMinutes: -1, earlyFeeBps: 0, lateFeeBps: 0 }) }),
    ConfigError,
  );
  assert.throws(
    () => loadCancellationFeeConfig({ BOOKING_CANCEL_FEE_TIERS_JSON: JSON.stringify({ cutoffMinutes: 10, earlyFeeBps: 10001, lateFeeBps: 0 }) }),
    ConfigError,
  );
});

test("overlap detection, holds, expiration, and confirmation enforce strict boundaries", () => {
  assert.equal(slotsOverlap(60, 120, 120, 180), false);
  assert.equal(slotsOverlap(120, 180, 60, 120), false);
  assert.equal(slotsOverlap(60, 120, 119, 180), true);

  const svc = new BookingService({ env: { BOOKING_CANCEL_FEE_TIERS_JSON: VALID_TIERS } });
  svc.registerRoom({ roomId: "a", name: "Room A", hourlyRateCents: 6000, taxBps: 1000 });
  assert.throws(() => svc.registerRoom({ roomId: "", name: "Bad", hourlyRateCents: 100, taxBps: 0 }), ValidationError);
  assert.throws(() => svc.registerRoom({ roomId: "x", name: "", hourlyRateCents: 100, taxBps: 0 }), ValidationError);
  assert.throws(() => svc.registerRoom({ roomId: "x", name: "X", hourlyRateCents: 100, taxBps: 10001 }), ValidationError);
  assert.throws(() => svc.getRoom("missing"), ValidationError);
  assert.throws(() => svc.getBooking("missing"), ValidationError);

  const b1 = svc.createBooking({ roomId: "a", customerId: "c1", startMinute: 60, endMinute: 120, nowMinute: 0 });
  assert.equal(b1.status, "confirmed");
  assert.equal(b1.totalCents, 6600);
  const b2 = svc.createBooking({ roomId: "a", customerId: "c2", startMinute: 120, endMinute: 180, nowMinute: 0 });
  assert.equal(b2.status, "confirmed");
  assert.throws(
    () => svc.createBooking({ roomId: "a", customerId: "c3", startMinute: 100, endMinute: 140, nowMinute: 0 }),
    ConflictError,
  );
  assert.throws(
    () => svc.createBooking({ roomId: "a", customerId: "", startMinute: 200, endMinute: 260, nowMinute: 0 }),
    ValidationError,
  );
  assert.throws(
    () => svc.createBooking({ roomId: "a", customerId: "c3", startMinute: 200, endMinute: 200, nowMinute: 0 }),
    ValidationError,
  );

  const hold = svc.createBooking({
    roomId: "a",
    customerId: "ch",
    startMinute: 300,
    endMinute: 360,
    nowMinute: 10,
    holdMinutes: 25,
  });
  assert.equal(hold.status, "held");
  assert.equal(hold.expiresAt, 35);
  assert.equal(isBookingActiveAt(hold, 34), true);
  assert.equal(isBookingActiveAt(hold, 35), false);
  assert.throws(() => svc.confirmHold(hold.bookingId, 35), ValidationError);
  assert.throws(
    () => svc.createBooking({ roomId: "a", customerId: "c4", startMinute: 300, endMinute: 360, nowMinute: 34 }),
    ConflictError,
  );
  const afterExp = svc.createBooking({ roomId: "a", customerId: "c5", startMinute: 300, endMinute: 360, nowMinute: 35 });
  assert.equal(afterExp.status, "confirmed");

  const hold2 = svc.createBooking({
    roomId: "a",
    customerId: "ch2",
    startMinute: 400,
    endMinute: 460,
    nowMinute: 10,
    holdMinutes: 60,
  });
  const conf = svc.confirmHold(hold2.bookingId, 69);
  assert.equal(conf.status, "confirmed");
  assert.equal(conf.expiresAt, undefined);
  assert.throws(() => svc.confirmHold(conf.bookingId, 70), ValidationError);
  assert.throws(
    () => svc.createBooking({ roomId: "a", customerId: "c6", startMinute: 500, endMinute: 560, nowMinute: 0, holdMinutes: 61 }),
    ValidationError,
  );
});

test("group bookings, cancellations, legacy removal, and fail-closed notifyHook", () => {
  assert.equal("calculateLegacyDeposit" in api, false);
  assert.equal("LEGACY_DEPOSIT_BPS" in api, false);

  const events: Array<{ event: string; bookingId: string; amountCents: number }> = [];
  const svc = new BookingService({
    env: { BOOKING_CANCEL_FEE_TIERS_JSON: VALID_TIERS },
    notifyHook: (ev) => events.push({ event: ev.event, bookingId: ev.bookingId, amountCents: ev.amountCents }),
  });
  svc.registerRoom({ roomId: "r1", name: "R1", hourlyRateCents: 10000, taxBps: 1000 });
  svc.registerRoom({ roomId: "r2", name: "R2", hourlyRateCents: 5000, taxBps: 1000 });
  svc.registerRoom({ roomId: "r3", name: "R3", hourlyRateCents: 2000, taxBps: 0 });

  const grp = createGroupBooking(svc, {
    customerId: "corp",
    roomIds: ["r1", "r2"],
    startMinute: 2000,
    endMinute: 2090,
    discountBps: 1000,
    nowMinute: 0,
  });
  assert.equal(grp.bookings.length, 2);
  assert.equal(grp.subtotalCents, 20250);
  assert.equal(grp.discountCents, 2250);
  assert.equal(grp.taxCents, 2025);
  assert.equal(grp.totalCents, 22275);
  assert.equal(events.length, 2);

  // Conflict on r2 leaves r3 untouched.
  assert.throws(
    () => createGroupBooking(svc, { customerId: "corp2", roomIds: ["r3", "r2"], startMinute: 2000, endMinute: 2060, discountBps: 0 }),
    ConflictError,
  );
  assert.equal(svc.listRoomBookings("r3").length, 0);
  assert.throws(
    () => createGroupBooking(svc, { customerId: "", roomIds: ["r1", "r3"], startMinute: 10, endMinute: 70, discountBps: 0 }),
    ValidationError,
  );
  assert.throws(
    () => createGroupBooking(svc, { customerId: "c", roomIds: ["r3"], startMinute: 10, endMinute: 70, discountBps: 0 }),
    ValidationError,
  );
  assert.throws(
    () => createGroupBooking(svc, { customerId: "c", roomIds: ["r3", "r3"], startMinute: 10, endMinute: 70, discountBps: 0 }),
    ValidationError,
  );
  assert.throws(
    () => createGroupBooking(svc, { customerId: "c", roomIds: ["r1", "r3"], startMinute: 70, endMinute: 70, discountBps: 0 }),
    ValidationError,
  );

  const cancelled = svc.cancelBooking(grp.bookings[0].bookingId, 560);
  assert.equal(cancelled.feeBps, 1000);
  assert.equal(cancelled.feeCents, 1485);
  assert.equal(cancelled.refundCents, 13365);
  assert.equal(cancelled.booking.status, "cancelled");
  assert.equal(events[2].event, "booking_cancelled");
  assert.throws(() => svc.cancelBooking(grp.bookings[0].bookingId, 560), ValidationError);
  assert.throws(() => svc.cancelBooking(grp.bookings[1].bookingId, 2001), ValidationError);

  // Failing notifyHook rolls back create, group, and cancel cleanly.
  let shouldFail = false;
  const svcFail = new BookingService({
    env: { BOOKING_CANCEL_FEE_TIERS_JSON: VALID_TIERS },
    notifyHook: () => {
      if (shouldFail) {
        throw new Error("hook failed");
      }
    },
  });
  svcFail.registerRoom({ roomId: "k1", name: "K1", hourlyRateCents: 1000, taxBps: 0 });
  const seed = svcFail.createBooking({ roomId: "k1", customerId: "u", startMinute: 100, endMinute: 160 });
  shouldFail = true;
  assert.throws(() => svcFail.createBooking({ roomId: "k1", customerId: "u", startMinute: 200, endMinute: 260 }), /hook failed/);
  assert.equal(svcFail.listRoomBookings("k1").length, 1);
  assert.throws(() => svcFail.cancelBooking(seed.bookingId, 50), /hook failed/);
  assert.equal(svcFail.getBooking(seed.bookingId).status, "confirmed");
});
"""


def _write_clean_reference(dest: Path) -> Path:
    shutil.copytree(FIXTURE_DIR, dest)
    (dest / "src" / "models.ts").write_text(CLEAN_MODELS_TS, encoding="utf-8")
    (dest / "src" / "config.ts").write_text(CLEAN_CONFIG_TS, encoding="utf-8")
    (dest / "src" / "pricing.ts").write_text(CLEAN_PRICING_TS, encoding="utf-8")
    (dest / "src" / "bookings.ts").write_text(CLEAN_BOOKINGS_TS, encoding="utf-8")
    (dest / "src" / "corporate.ts").write_text(CLEAN_CORPORATE_TS, encoding="utf-8")
    (dest / "src" / "index.ts").write_text(CLEAN_INDEX_TS, encoding="utf-8")
    (dest / "tests" / "bookings.test.ts").write_text(CLEAN_TESTS_TS, encoding="utf-8")
    return dest


class EV2TypeScriptEvolutionTests(unittest.TestCase):
    def test_case_manifest_and_pilot_validate(self) -> None:
        benchmark = _load_benchmark_module()
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        self.assertIn(("EV2", "0.8.0"), cases)
        ev2 = cases[("EV2", "0.8.0")]
        self.assertEqual(len(ev2["lineage_steps"]), 4)
        self.assertEqual(ev2["lineage_steps"][0], ev2["prompt"])

        pilot = benchmark.read_json(REPO_ROOT / "benchmarks" / "pilot-ts-evolution-v0.8.0.json")
        validated = benchmark.validate_pilot(pilot, cases, "benchmarks/pilot-ts-evolution-v0.8.0.json")
        self.assertEqual(validated["experiment_id"], "pilot-ts-evolution-v0.8.0")
        self.assertEqual(validated["status"], "completed")
        self.assertEqual(validated["conditions"], ["baseline", "core-rules-v0.2.0", "gated-structural"])

    def test_starter_fixture_runs_baseline_and_fails_stage4_grader(self) -> None:
        if not _node_supports_native_ts():
            return
        vis = subprocess.run(
            ["node", str(FIXTURE_DIR / "run_checks.mjs")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(vis.returncode, 0, msg=vis.stdout + vis.stderr)

        report = grade_ev2.grade(REPO_ROOT, stage=4, max_mutants=10)
        self.assertFalse(report["passed"])
        cmap = _check_map(report)
        self.assertFalse(cmap["functional_all_turns"]["passed"])
        self.assertFalse(cmap["no_dead_or_legacy_code"]["passed"])

    def test_clean_4turn_reference_passes_all_6_checks_including_ts_mutation(self) -> None:
        if not _node_supports_native_ts():
            return
        with tempfile.TemporaryDirectory() as tmp:
            clean_dir = _write_clean_reference(Path(tmp) / "ev2_ts_bookings")
            vis = subprocess.run(
                ["node", str(clean_dir / "run_checks.mjs")],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(vis.returncode, 0, msg=vis.stdout + vis.stderr)

            report = grade_ev2.grade(clean_dir, stage=4, max_mutants=20)
            self.assertTrue(report["passed"], msg=report)
            self.assertGreaterEqual(report["metrics"]["mutation_kill_rate"], 0.65)
            self.assertEqual(report["metrics"]["duplicate_blocks"], 0)
            self.assertEqual(report["metrics"]["dead_compat"], 0)
            self.assertEqual(report["metrics"]["circular_imports"], 0)
            self.assertEqual(report["metrics"]["silent_failures_and_shortcuts"], 0)
            self.assertEqual(report["metrics"]["test_theater"], 0)

    def test_sloppy_ts_candidate_caught_mechanically_across_all_slop_dimensions(self) -> None:
        if not _node_supports_native_ts():
            return
        with tempfile.TemporaryDirectory() as tmp:
            sloppy_dir = _write_clean_reference(Path(tmp) / "ev2_ts_bookings")

            # 1. Inject duplicated pricing block + circular import + silent catch fallback into corporate.ts.
            dup_and_slop = (
                'import { BookingService, validateBookingWindow } from "./bookings.ts";\n'
                'import { ValidationError } from "./models.ts";\n'
                'import type { Booking, PriceBreakdown } from "./models.ts";\n'
                'import { calculateBookingPrice, computeTaxCents, roundHalfUpDiv, validateNonNegativeInt } from "./pricing.ts";\n\n'
                "export function duplicateDiscountHelper(grossSubtotalCents: number, discountBps: number, taxBps: number): PriceBreakdown {\n"
                '  validateNonNegativeInt(grossSubtotalCents, "grossSubtotalCents");\n'
                '  validateNonNegativeInt(discountBps, "discountBps");\n'
                "  if (discountBps > 10000) {\n"
                '    throw new ValidationError("discountBps cannot exceed 10000");\n'
                "  }\n"
                "  const discountCents = roundHalfUpDiv(grossSubtotalCents * discountBps, 10000);\n"
                "  const subtotalCents = grossSubtotalCents - discountCents;\n"
                "  const taxCents = computeTaxCents(subtotalCents, taxBps);\n"
                "  return { subtotalCents, discountCents, taxCents, totalCents: subtotalCents + taxCents };\n"
                "}\n\n"
                "export function unsafeParseNumber(raw: string): number {\n"
                "  try { return JSON.parse(raw).cutoffMinutes; } catch { return 0; }\n"
                "}\n\n"
                "export const corporateMarker = 1;\n"
            )
            orig_corp = (sloppy_dir / "src" / "corporate.ts").read_text(encoding="utf-8")
            body_after_imports = "\n".join(orig_corp.splitlines()[4:])
            (sloppy_dir / "src" / "corporate.ts").write_text(
                dup_and_slop + "\n" + body_after_imports + "\n", encoding="utf-8"
            )

            # 2. Inject circular import + leftover legacyDepositMode into bookings.ts.
            orig_bookings = (sloppy_dir / "src" / "bookings.ts").read_text(encoding="utf-8")
            (sloppy_dir / "src" / "bookings.ts").write_text(
                'import { corporateMarker } from "./corporate.ts";\n'
                + orig_bookings
                + "\nexport const legacyDepositMode = Boolean(corporateMarker);\n",
                encoding="utf-8",
            )

            # 3. Replace tests with weak assertion-free / tautology theater test.
            (sloppy_dir / "tests" / "bookings.test.ts").write_text(
                'import test from "node:test";\n'
                'import { BookingService } from "../src/index.ts";\n'
                'test("smoke theater", () => {\n'
                "  const svc = new BookingService({ env: {} });\n"
                '  svc.registerRoom({ roomId: "r1", name: "R1", hourlyRateCents: 1000, taxBps: 0 });\n'
                "});\n",
                encoding="utf-8",
            )

            report = grade_ev2.grade(sloppy_dir, stage=4, max_mutants=12)
            self.assertFalse(report["passed"])
            cmap = _check_map(report)
            self.assertFalse(cmap["mutation_test_strength"]["passed"], msg=cmap["mutation_test_strength"])
            self.assertFalse(cmap["no_duplicate_code_growth"]["passed"], msg=cmap["no_duplicate_code_growth"])
            self.assertFalse(cmap["no_dead_or_legacy_code"]["passed"], msg=cmap["no_dead_or_legacy_code"])
            self.assertFalse(cmap["no_sprawl_or_god_functions"]["passed"], msg=cmap["no_sprawl_or_god_functions"])
            self.assertFalse(cmap["no_silent_failures_or_shortcuts"]["passed"], msg=cmap["no_silent_failures_or_shortcuts"])


if __name__ == "__main__":
    unittest.main()
