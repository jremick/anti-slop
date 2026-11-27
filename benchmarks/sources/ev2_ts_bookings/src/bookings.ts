import { loadBookingConfig } from "./config.ts";
import type { BookingConfig } from "./config.ts";
import { ValidationError } from "./models.ts";
import type { Booking, CreateBookingInput, Room } from "./models.ts";
import { calculateBookingPrice, validateNonNegativeInt, validatePositiveInt } from "./pricing.ts";

export interface BookingServiceOptions {
  readonly env?: Record<string, string | undefined>;
}

export class BookingService {
  readonly config: BookingConfig;
  private readonly rooms: Map<string, Room> = new Map();
  private readonly bookings: Map<string, Booking> = new Map();
  private seq = 0;

  constructor(options: BookingServiceOptions = {}) {
    this.config = loadBookingConfig(options.env);
  }

  private nextId(prefix: string): string {
    this.seq += 1;
    return `${prefix}_${String(this.seq).padStart(4, "0")}`;
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

  createBooking(input: CreateBookingInput): Booking {
    if (typeof input.customerId !== "string" || input.customerId.trim() === "") {
      throw new ValidationError("customerId must be a non-empty string");
    }
    validateNonNegativeInt(input.startMinute, "startMinute");
    validatePositiveInt(input.endMinute, "endMinute");
    if (input.endMinute <= input.startMinute) {
      throw new ValidationError("endMinute must be strictly greater than startMinute");
    }
    const room = this.getRoom(input.roomId);
    const duration = input.endMinute - input.startMinute;
    const price = calculateBookingPrice(room, duration, {
      legacyDepositMode: input.legacyDepositMode,
    });
    const booking: Booking = {
      bookingId: this.nextId("bkg"),
      roomId: room.roomId,
      customerId: input.customerId.trim(),
      startMinute: input.startMinute,
      endMinute: input.endMinute,
      status: "confirmed",
      subtotalCents: price.subtotalCents,
      discountCents: price.discountCents,
      taxCents: price.taxCents,
      totalCents: price.totalCents,
      depositCents: price.depositCents,
    };
    this.bookings.set(booking.bookingId, booking);
    return booking;
  }
}
