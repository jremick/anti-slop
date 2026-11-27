import { ValidationError } from "./models.ts";
import type { PriceBreakdown, Room } from "./models.ts";

export const LEGACY_DEPOSIT_BPS = 2500;

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

export function computeTaxCents(taxableCents: number, taxBps: number): number {
  validateNonNegativeInt(taxableCents, "taxableCents");
  validateNonNegativeInt(taxBps, "taxBps");
  if (taxBps > 10000) {
    throw new ValidationError("taxBps cannot exceed 10000");
  }
  return Math.floor((taxableCents * taxBps + 5000) / 10000);
}

export function calculateLegacyDeposit(subtotalCents: number): number {
  validateNonNegativeInt(subtotalCents, "subtotalCents");
  return Math.floor((subtotalCents * LEGACY_DEPOSIT_BPS + 5000) / 10000);
}

export function calculateBookingPrice(
  room: Room,
  durationMinutes: number,
  options?: { readonly legacyDepositMode?: boolean },
): PriceBreakdown {
  validatePositiveInt(room.hourlyRateCents, "hourlyRateCents");
  validatePositiveInt(durationMinutes, "durationMinutes");
  if (durationMinutes % 60 !== 0) {
    throw new ValidationError("Starter pricing only supports whole-hour durations");
  }
  const hours = durationMinutes / 60;
  const subtotalCents = room.hourlyRateCents * hours;
  const taxCents = computeTaxCents(subtotalCents, room.taxBps);
  const depositCents = options?.legacyDepositMode === true
    ? calculateLegacyDeposit(subtotalCents)
    : 0;
  return {
    subtotalCents,
    discountCents: 0,
    taxCents,
    totalCents: subtotalCents + taxCents,
    depositCents,
  };
}
