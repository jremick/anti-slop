import { ConfigError } from "./models.ts";

export interface BookingConfig {
  readonly maxHoldMinutes: number;
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
