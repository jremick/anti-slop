export class BookingError extends Error {
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
  readonly depositCents: number;
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
  readonly depositCents?: number;
}

export interface CreateBookingInput {
  readonly roomId: string;
  readonly customerId: string;
  readonly startMinute: number;
  readonly endMinute: number;
  readonly legacyDepositMode?: boolean;
}
