"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { Hours } from "@/lib/backend/business-sections";
import {
  WEEKDAYS,
  type BlockCreated,
  type Booking,
  type BookingDetail,
  type CalendarAccount,
  type CancelledBooking,
  type CancelPreview,
  type CapacitySlots,
  type ReservasService,
  type ReservasSettings,
  type ServicesSlots,
  type SlotOffer,
  type StaffMember,
  type WaitlistEntry,
} from "@/lib/backend/reservas";
import { checkCategory, checkDay, checkDuration, checkPrice, type Checked, type RuleProblem } from "@/lib/business-rules";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Server Actions of Reservas (spec 043, T021). Zod on the server, a fresh 60 s
 * token per call; the API decides and its answer travels back as
 * `{ok:false,status,code,info}` — a 409 names the case (`slot_taken` with its
 * `first_fit`, `invalid_transition`, `live_reservations` with its `count`…), a
 * 412 is `stale`.
 *
 * Only the person of a client with the `reservas` module may call these; the
 * API answers 403 to anyone else, and the console says it first.
 *
 * Writes that create take the `idempotencyKey` the screen generated for that
 * submit (and keeps on a retry); writes that change a booking or the settings
 * take the `version` the screen read, sent as `If-Match`.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

async function reservasPrincipal() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok" || res.principal.kind !== "client") return null;
  return res.principal.modules.includes("reservas") ? res.principal : null;
}

const id = z.string().uuid();
const key = z.string().uuid();
const version = z.number().int().min(0);
const day = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/);
const name = z.string().trim().min(1).max(120);
const phone = z
  .string()
  .trim()
  .max(32)
  .regex(/^\+?[0-9 ()-]{6,24}$/)
  .nullable();
const note = z.string().trim().max(500).nullable();
const party = z.number().int().min(1).max(1000);

const range = z
  .object({ from: time, to: time })
  .refine((r) => r.from < r.to, { message: "from must be before to" });
const dayHours = z
  .array(range)
  .max(2)
  .refine((rs) => rs.length < 2 || rs[0]!.to <= rs[1]!.from, { message: "ranges overlap" });
const weekHours = z.object(Object.fromEntries(WEEKDAYS.map((d) => [d, dayHours])) as Record<(typeof WEEKDAYS)[number], typeof dayHours>);

// ── reads ────────────────────────────────────────────────────────────────

const idSchema = z.object({ id });

export async function bookingDetailAction(raw: unknown): Promise<ActionResult<BookingDetail>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasBooking(p.id));
}

const serviceSlotsSchema = z.object({ date: day, service_id: id, staff_id: id.optional(), exclude: id.optional() });
export async function serviceSlotsAction(raw: unknown): Promise<ActionResult<ServicesSlots>> {
  const p = serviceSlotsSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasServiceSlots(p));
}

const capacitySlotsSchema = z.object({ date: day, party_size: party, walkin: z.boolean().optional(), exclude: id.optional() });
export async function capacitySlotsAction(raw: unknown): Promise<ActionResult<CapacitySlots>> {
  const p = capacitySlotsSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCapacitySlots(p));
}

export async function cancelPreviewAction(raw: unknown): Promise<ActionResult<CancelPreview>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCancelPreview(p.id));
}

// ── bookings ─────────────────────────────────────────────────────────────

const createSchema = z.object({
  date: day,
  time,
  staff_id: id.nullable().optional(),
  service_id: id.nullable().optional(),
  party_size: party.nullable().optional(),
  contact: z.object({ name, phone }),
  note: note.default(null),
  join_waitlist: z.boolean().default(false),
  notify: z.boolean().default(true),
  idempotencyKey: key,
});
export async function createBookingAction(raw: unknown): Promise<ActionResult<Booking>> {
  const { idempotencyKey, ...body } = createSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCreateBooking(body, idempotencyKey));
}

const moveSchema = z.object({
  id,
  version,
  date: day.optional(),
  time: time.optional(),
  staff_id: id.optional(),
  party_size: party.optional(),
  // Enmienda 2026-10-22: absent leaves the note as it is, `null` clears it.
  note: note.optional(),
  notify: z.boolean().default(true),
});
export async function moveBookingAction(raw: unknown): Promise<ActionResult<Booking>> {
  const { id: bookingId, version: v, ...body } = moveSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasMoveBooking(bookingId, body, v));
}

const cancelSchema = z.object({ id, version, notify: z.boolean().default(true), offer_slot: z.boolean().default(false) });
export async function cancelBookingAction(raw: unknown): Promise<ActionResult<CancelledBooking>> {
  const { id: bookingId, version: v, ...body } = cancelSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCancelBooking(bookingId, body, v));
}

const transitionSchema = z.object({
  id,
  version,
  action: z.enum(["confirm", "request_confirmation", "arrive", "noshow", "undo"]),
});
export async function bookingTransitionAction(raw: unknown): Promise<ActionResult<Booking>> {
  const p = transitionSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasTransition(p.id, p.action, p.version));
}

const walkinSchema = z.object({ party_size: party, name: name.nullable(), idempotencyKey: key });
export async function walkinAction(raw: unknown): Promise<ActionResult<Booking>> {
  const { idempotencyKey, ...body } = walkinSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasWalkin(body, idempotencyKey));
}

// ── blocks (Aforo) ───────────────────────────────────────────────────────

const blockSchema = z
  .object({ date: day, from: time, until: time, label: z.string().trim().min(1).max(120), idempotencyKey: key })
  .refine((b) => b.from <= b.until, { message: "from must not be after until" });
export async function createBlockAction(raw: unknown): Promise<ActionResult<BlockCreated>> {
  const { idempotencyKey, ...body } = blockSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCreateBlock(body, idempotencyKey));
}

export async function removeBlockAction(raw: unknown): Promise<ActionResult<null>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasRemoveBlock(p.id));
}

// ── waitlist and offers ──────────────────────────────────────────────────

const waitlistSchema = z.union([
  z.object({
    name,
    phone,
    party_size: party,
    date: day,
    time,
    in_person: z.boolean().default(false),
    idempotencyKey: key,
  }),
  z.object({
    name,
    phone,
    service_id: id,
    staff_id: id.nullable(),
    date: day.nullable(),
    until: day.nullable(),
    idempotencyKey: key,
  }),
]);
export async function addWaitlistAction(raw: unknown): Promise<ActionResult<WaitlistEntry>> {
  const { idempotencyKey, ...body } = waitlistSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasAddWaitlist(body, idempotencyKey));
}

export async function removeWaitlistAction(raw: unknown): Promise<ActionResult<null>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasRemoveWaitlist(p.id));
}

export async function offerWaitlistAction(raw: unknown): Promise<ActionResult<SlotOffer>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasOfferWaitlist(p.id));
}

export async function stopOfferAction(raw: unknown): Promise<ActionResult<SlotOffer>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasStopOffer(p.id));
}

// ── settings, hours, team, services ──────────────────────────────────────

const shift = z.object({ name: z.string().trim().min(1).max(40), from: time, to: time });
const scheduleSchema = z.union([
  z.object({
    model: z.literal("shifts"),
    step_minutes: z.union([z.literal(15), z.literal(30), z.literal(60), z.literal(90), z.literal(120)]),
    shifts: z.array(shift).min(1).max(6),
  }),
  z.object({
    model: z.literal("slots"),
    step_minutes: z.union([z.literal(15), z.literal(30), z.literal(60), z.literal(90), z.literal(120)]),
    from: time,
    to: time,
  }),
]);
const patchSchema = z
  .object({
    waitlist: z
      .object({
        enabled: z.boolean().optional(),
        lead_minutes: z.union([z.literal(60), z.literal(120), z.literal(240), z.literal(1440)]).optional(),
      })
      .strict()
      .optional(),
    agent: z
      .object({
        min_notice_minutes: z.number().int().min(0).max(1440).optional(),
        max_days_ahead: z.number().int().min(1).max(365).optional(),
      })
      .strict()
      .optional(),
    confirmation: z
      .object({ enabled: z.boolean().optional(), when: z.enum(["24h", "same_day_12", "3h"]).optional() })
      .strict()
      .optional(),
    reminder_enabled: z.boolean().optional(),
    release_unconfirmed: z.boolean().optional(),
    slot_step_minutes: z.union([z.literal(15), z.literal(30), z.literal(60)]).optional(),
    capacity: z
      .object({
        seats: z.number().int().min(1).max(10000).optional(),
        stay_minutes: z
          .number()
          .int()
          .min(30)
          .max(480)
          .refine((m) => m % 15 === 0)
          .optional(),
        max_party: z.number().int().min(1).optional(),
        walkin_hold: z.number().int().min(0).optional(),
        schedule: scheduleSchema.optional(),
      })
      .strict()
      .optional(),
  })
  .strict();
const settingsSchema = z.object({ version, patch: patchSchema });
export async function patchSettingsAction(raw: unknown): Promise<ActionResult<ReservasSettings>> {
  const p = settingsSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasPatchSettings(p.patch, p.version));
}

/**
 * Spec 056 (5.6): a value that breaks a rule of `lib/business-rules.ts` (the
 * API's, the ficha's) answers as the API would, `422 {code, field, day?}`, so the
 * screen says which value fails and why. A shape that is not the screen's (a
 * programming error) still throws.
 */
function refused(problem: RuleProblem): ActionResult<never> {
  return { ok: false, status: 422, message: "invalid", code: problem.code, info: { field: problem.field, ...(problem.day ? { day: problem.day } : {}) } };
}

const firstProblem = (...checks: (Checked<unknown> | null)[]): RuleProblem | null => {
  for (const c of checks) if (c && !c.ok) return c.problem;
  return null;
};

const shiftIn = z.object({ open: z.string(), close: z.string() }).strict();
const hoursPatchSchema = z
  .object({
    revision: version,
    days: z.record(z.enum(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]), z.array(shiftIn).max(50)),
  })
  .strict();
/** Spec 056 (5.1, 5.3): the ficha's week, only the touched days, with the revision read. */
export async function patchBusinessHoursAction(raw: unknown): Promise<ActionResult<Hours>> {
  const p = hoursPatchSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  const problem = firstProblem(...Object.entries(p.days).map(([day, shifts]) => checkDay(shifts ?? [], day)));
  if (problem) return refused(problem);
  return run(() => backendFor(principal).reservasPatchBusinessHours(p));
}

const email = z.string().trim().email().max(254).nullable();
const staffSchema = z.object({ name, email, hours: weekHours.nullable(), idempotencyKey: key });
export async function createStaffAction(raw: unknown): Promise<ActionResult<StaffMember>> {
  const { idempotencyKey, ...body } = staffSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCreateStaff(body, idempotencyKey));
}

const staffPatchSchema = z.object({
  id,
  name: name.optional(),
  email: email.optional(),
  hours: weekHours.nullable().optional(),
  position: z.number().int().min(0).optional(),
});
export async function updateStaffAction(raw: unknown): Promise<ActionResult<StaffMember>> {
  const { id: staffId, ...body } = staffPatchSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasUpdateStaff(staffId, body));
}

export async function archiveStaffAction(raw: unknown): Promise<ActionResult<null>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasArchiveStaff(p.id));
}

// ── calendars (§8, P3) ───────────────────────────────────────────────────

export async function calendarAccountAction(): Promise<ActionResult<CalendarAccount>> {
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasCalendar());
}

/** `calendar_id: null` lets the calendar go. */
const staffCalendarSchema = z.object({ id, calendar_id: z.string().trim().min(1).max(255).nullable() });
export async function staffCalendarAction(raw: unknown): Promise<ActionResult<StaffMember>> {
  const p = staffCalendarSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasSetStaffCalendar(p.id, p.calendar_id));
}

const price = z
  .object({ kind: z.enum(["none", "free", "amount"]), amount_minor: z.number().int().optional() })
  .strict();
const serviceSchema = z.object({
  name,
  duration_minutes: z.number().int(),
  price,
  price_currency: z.string().regex(/^[A-Z]{3}$/).optional(),
  category: z.string().nullable().optional(),
  staff_ids: z.array(id).max(200).nullable(),
  idempotencyKey: key,
});
/** Spec 056 (5.2): the ficha's rules — 5 to 480 minutes in steps of 5, an amount up to 10¹², a category of 40. */
function serviceProblem(body: { duration_minutes?: number; price?: z.infer<typeof price>; category?: string | null }): RuleProblem | null {
  return firstProblem(
    body.duration_minutes === undefined ? null : checkDuration(body.duration_minutes),
    body.price === undefined ? null : checkPrice(body.price.kind, body.price.amount_minor),
    body.category == null ? null : checkCategory(body.category),
  );
}

export async function createServiceAction(raw: unknown): Promise<ActionResult<ReservasService>> {
  const { idempotencyKey, ...body } = serviceSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  const problem = serviceProblem(body);
  if (problem) return refused(problem);
  return run(() => backendFor(principal).reservasCreateService(body, idempotencyKey));
}

/** Only what changed (5.3); never the name: Reservas does not rename (5.4). */
const servicePatchSchema = z
  .object({
    id,
    duration_minutes: z.number().int().optional(),
    price: price.optional(),
    price_currency: z.string().regex(/^[A-Z]{3}$/).optional(),
    category: z.string().nullable().optional(),
    staff_ids: z.array(id).max(200).nullable().optional(),
    position: z.number().int().min(0).optional(),
  })
  .strict();
export async function updateServiceAction(raw: unknown): Promise<ActionResult<ReservasService>> {
  const { id: serviceId, ...body } = servicePatchSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  const problem = serviceProblem(body);
  if (problem) return refused(problem);
  return run(() => backendFor(principal).reservasUpdateService(serviceId, body));
}

export async function archiveServiceAction(raw: unknown): Promise<ActionResult<null>> {
  const p = idSchema.parse(raw);
  const principal = await reservasPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).reservasArchiveService(p.id));
}
