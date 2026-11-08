import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../actions");

const ID = "5b0a5f0e-7c2d-4c39-9d6f-1e1c9f3a1b22";
const STAFF = "8c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f";
const SERVICE = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
const KEY = "0f8b2c3e-6a1d-4b7e-9c2f-1a2b3c4d5e6f";
const forbidden = { ok: false, status: 403, message: "forbidden" };

/** Spec 043 (T021): Reservas's actions are for a client person with the module, nobody else. */
describe("reservas actions", () => {
  it("create a booking with the submit's Idempotency-Key, never in the body", async () => {
    h.setClient(["panel", "reservas"]);
    h.backend.reservasCreateBooking.mockResolvedValue({ id: ID });
    const r = await actions.createBookingAction({
      date: "2026-10-23",
      time: "10:00",
      staff_id: STAFF,
      service_id: SERVICE,
      contact: { name: "  Ana Pérez ", phone: "+56 9 1111 2222" },
      join_waitlist: true,
      idempotencyKey: KEY,
    });
    expect(r).toEqual({ ok: true, data: { id: ID } });
    expect(h.backend.reservasCreateBooking).toHaveBeenCalledWith(
      {
        date: "2026-10-23",
        time: "10:00",
        staff_id: STAFF,
        service_id: SERVICE,
        contact: { name: "Ana Pérez", phone: "+56 9 1111 2222" },
        note: null,
        join_waitlist: true,
        notify: true,
      },
      KEY,
    );
  });

  it("move, cancel and every transition carry the version they read (If-Match)", async () => {
    h.setClient(["reservas"]);
    await actions.moveBookingAction({ id: ID, version: 3, date: "2026-10-24", time: "11:30", notify: false });
    expect(h.backend.reservasMoveBooking).toHaveBeenCalledWith(ID, { date: "2026-10-24", time: "11:30", notify: false }, 3);
    // Enmienda 2026-10-22: «Cambiar» of Aforo sends the note — trimmed, and `null` clears it.
    await actions.moveBookingAction({ id: ID, version: 3, date: "2026-10-24", time: "21:00", party_size: 4, note: "  Terraza ", notify: true });
    expect(h.backend.reservasMoveBooking).toHaveBeenLastCalledWith(ID, { date: "2026-10-24", time: "21:00", party_size: 4, note: "Terraza", notify: true }, 3);
    await actions.moveBookingAction({ id: ID, version: 3, date: "2026-10-24", time: "21:00", note: null, notify: true });
    expect(h.backend.reservasMoveBooking).toHaveBeenLastCalledWith(ID, { date: "2026-10-24", time: "21:00", note: null, notify: true }, 3);
    await actions.cancelBookingAction({ id: ID, version: 4, notify: true, offer_slot: true });
    expect(h.backend.reservasCancelBooking).toHaveBeenCalledWith(ID, { notify: true, offer_slot: true }, 4);
    for (const action of ["confirm", "request_confirmation", "arrive", "noshow", "undo"] as const) {
      await actions.bookingTransitionAction({ id: ID, version: 5, action });
      expect(h.backend.reservasTransition).toHaveBeenLastCalledWith(ID, action, 5);
    }
  });

  it("a stale version and a taken slot travel back with their code and info", async () => {
    h.setClient(["reservas"]);
    h.fail("reservasMoveBooking", 412, "", "stale");
    expect(await actions.moveBookingAction({ id: ID, version: 1, notify: true })).toMatchObject({ ok: false, status: 412, code: "stale" });
    h.fail("reservasCreateBooking", 409, "", "slot_taken", { first_fit: { date: "2026-10-23", time: "21:30" } });
    const r = await actions.createBookingAction({
      date: "2026-10-23",
      time: "21:00",
      party_size: 10,
      contact: { name: "Grupo", phone: null },
      idempotencyKey: KEY,
    });
    expect(r).toMatchObject({ ok: false, status: 409, code: "slot_taken", info: { first_fit: { time: "21:30" } } });
  });

  it("settings go with If-Match; mode and kind are not editable", async () => {
    h.setClient(["reservas"]);
    await actions.patchSettingsAction({ version: 4, patch: { waitlist: { enabled: true, lead_minutes: 240 } } });
    expect(h.backend.reservasPatchSettings).toHaveBeenCalledWith({ waitlist: { enabled: true, lead_minutes: 240 } }, 4);
    await expect(actions.patchSettingsAction({ version: 4, patch: { mode: "services" } })).rejects.toThrow();
    await expect(actions.patchSettingsAction({ version: 4, patch: { waitlist: { lead_minutes: 90 } } })).rejects.toThrow();
    await expect(actions.patchSettingsAction({ version: 4, patch: { capacity: { stay_minutes: 100 } } })).rejects.toThrow();
  });

  it("hours (spec 056): only the touched days, with the revision read", async () => {
    h.setClient(["reservas"]);
    const days = { tue: [{ open: "10:00", close: "18:00" }], sun: [] };
    await actions.patchBusinessHoursAction({ revision: 3, days });
    expect(h.backend.reservasPatchBusinessHours).toHaveBeenCalledWith({ revision: 3, days });
    // Up to six shifts, night ones too (they close the next day), and 24:00 closes.
    const six = Array.from({ length: 6 }, (_, i) => ({ open: `${String(8 + 2 * i).padStart(2, "0")}:00`, close: `${String(9 + 2 * i).padStart(2, "0")}:00` }));
    await actions.patchBusinessHoursAction({ revision: 3, days: { mon: six, fri: [{ open: "22:00", close: "02:00" }], sat: [{ open: "00:00", close: "24:00" }] } });
    expect(h.backend.reservasPatchBusinessHours).toHaveBeenCalledTimes(2);
  });

  it("hours (spec 056): a rule that fails is a 422 with its code and day, without asking the API", async () => {
    h.setClient(["reservas"]);
    h.backend.reservasPatchBusinessHours.mockClear();
    const seven = Array.from({ length: 7 }, (_, i) => ({ open: `0${i}:00`, close: `0${i}:30` }));
    for (const [days, code, day] of [
      [{ wed: seven }, "too_many_shifts", "wed"],
      [{ wed: [{ open: "10:07", close: "12:00" }] }, "bad_step", "wed"],
      [{ thu: [{ open: "09:00", close: "13:00" }, { open: "12:00", close: "15:00" }] }, "overlap", "thu"],
    ] as const) {
      expect(await actions.patchBusinessHoursAction({ revision: 3, days })).toEqual({
        ok: false,
        status: 422,
        message: "invalid",
        code,
        info: expect.objectContaining({ day }),
      });
    }
    expect(h.backend.reservasPatchBusinessHours).not.toHaveBeenCalled();
    await expect(actions.patchBusinessHoursAction({ days: {} })).rejects.toThrow();
  });

  it("services (spec 056): the ficha's rules, said as a 422 with the field", async () => {
    h.setClient(["reservas"]);
    h.backend.reservasCreateService.mockClear();
    const base = { name: "Masaje", duration_minutes: 50, price: { kind: "free" }, staff_ids: null, idempotencyKey: KEY };
    await actions.createServiceAction(base);
    expect(h.backend.reservasCreateService).toHaveBeenCalledWith({ name: "Masaje", duration_minutes: 50, price: { kind: "free" }, staff_ids: null }, KEY);
    for (const [patch, code, field] of [
      [{ duration_minutes: 7 }, "bad_duration", "duration_min"],
      [{ duration_minutes: 485 }, "bad_duration", "duration_min"],
      [{ price: { kind: "amount", amount_minor: 10 ** 12 + 1 } }, "amount_too_large", "price"],
      [{ price: { kind: "amount" } }, "price_amount_required", "price"],
      [{ category: "x".repeat(41) }, "category_too_long", "category"],
    ] as const) {
      const failed = { ok: false, status: 422, message: "invalid", code, info: { field } };
      expect(await actions.createServiceAction({ ...base, ...patch })).toEqual(failed);
      expect(await actions.updateServiceAction({ id: SERVICE, ...patch })).toEqual(failed);
    }
    expect(h.backend.reservasCreateService).toHaveBeenCalledTimes(1);
    // Only what changed travels; the name is never sent on an edit.
    await actions.updateServiceAction({ id: SERVICE, price: { kind: "amount", amount_minor: 20000 } });
    expect(h.backend.reservasUpdateService).toHaveBeenLastCalledWith(SERVICE, { price: { kind: "amount", amount_minor: 20000 } });
    await expect(actions.updateServiceAction({ id: SERVICE, name: "Otro" })).rejects.toThrow();
  });

  it("staff (spec 056, 11.3): an email of 254 characters at most", async () => {
    h.setClient(["reservas"]);
    await actions.createStaffAction({ name: "Nora", email: "nora@cultor.cl", hours: null, idempotencyKey: KEY });
    await expect(actions.createStaffAction({ name: "Nora", email: `${"a".repeat(250)}@x.co`, hours: null, idempotencyKey: KEY })).rejects.toThrow();
  });

  it("the calendars: read the account, link one, and let it go with null", async () => {
    h.setClient(["reservas"]);
    await actions.calendarAccountAction();
    expect(h.backend.reservasCalendar).toHaveBeenCalled();
    await actions.staffCalendarAction({ id: STAFF, calendar_id: "lucia@agenda" });
    expect(h.backend.reservasSetStaffCalendar).toHaveBeenCalledWith(STAFF, "lucia@agenda");
    await actions.staffCalendarAction({ id: STAFF, calendar_id: null });
    expect(h.backend.reservasSetStaffCalendar).toHaveBeenCalledWith(STAFF, null);
    await expect(actions.staffCalendarAction({ id: "nope", calendar_id: null })).rejects.toThrow();

    h.setClient(["panel"]);
    await expect(actions.calendarAccountAction()).resolves.toEqual(forbidden);
    await expect(actions.staffCalendarAction({ id: STAFF, calendar_id: null })).resolves.toEqual(forbidden);
  });

  it("team, services, blocks, walk-ins and the waitlist reach their routes", async () => {
    h.setClient(["reservas"]);
    await actions.createStaffAction({ name: "Lucía", email: null, hours: null, idempotencyKey: KEY });
    expect(h.backend.reservasCreateStaff).toHaveBeenCalledWith({ name: "Lucía", email: null, hours: null }, KEY);
    await actions.createServiceAction({ name: "Corte", duration_minutes: 45, price: { kind: "amount", amount_minor: 15000 }, staff_ids: null, idempotencyKey: KEY });
    expect(h.backend.reservasCreateService).toHaveBeenCalledWith(
      { name: "Corte", duration_minutes: 45, price: { kind: "amount", amount_minor: 15000 }, staff_ids: null },
      KEY,
    );
    await actions.archiveStaffAction({ id: STAFF });
    expect(h.backend.reservasArchiveStaff).toHaveBeenCalledWith(STAFF);
    await actions.createBlockAction({ date: "2026-10-24", from: "20:00", until: "22:00", label: "Cena de empresa", idempotencyKey: KEY });
    expect(h.backend.reservasCreateBlock).toHaveBeenCalledWith(
      { date: "2026-10-24", from: "20:00", until: "22:00", label: "Cena de empresa" },
      KEY,
    );
    await actions.walkinAction({ party_size: 4, name: null, idempotencyKey: KEY });
    expect(h.backend.reservasWalkin).toHaveBeenCalledWith({ party_size: 4, name: null }, KEY);
    await actions.addWaitlistAction({ name: "Marta", phone: null, party_size: 2, date: "2026-10-23", time: "20:30", idempotencyKey: KEY });
    expect(h.backend.reservasAddWaitlist).toHaveBeenCalledWith(
      { name: "Marta", phone: null, party_size: 2, date: "2026-10-23", time: "20:30", in_person: false },
      KEY,
    );
    // Servicios: «Apuntar a alguien» — a service, anyone or someone, any opening until a day.
    await actions.addWaitlistAction({ name: "Rosa", phone: "+56 9 3333 4444", service_id: SERVICE, staff_id: null, date: null, until: "2026-10-29", idempotencyKey: KEY });
    expect(h.backend.reservasAddWaitlist).toHaveBeenLastCalledWith(
      { name: "Rosa", phone: "+56 9 3333 4444", service_id: SERVICE, staff_id: null, date: null, until: "2026-10-29" },
      KEY,
    );
    await actions.stopOfferAction({ id: ID });
    expect(h.backend.reservasStopOffer).toHaveBeenCalledWith(ID);
    await actions.capacitySlotsAction({ date: "2026-10-23", party_size: 4, walkin: true });
    expect(h.backend.reservasCapacitySlots).toHaveBeenCalledWith({ date: "2026-10-23", party_size: 4, walkin: true });
  });

  it("deny a client without Reservas and a partner member, without calling the backend", async () => {
    h.backend.reservasBooking.mockClear();
    h.backend.reservasCreateBooking.mockClear();
    h.setClient(["panel", "inbox", "usage"]);
    expect(await actions.bookingDetailAction({ id: ID })).toEqual(forbidden);
    h.setRole("owner");
    expect(await actions.bookingDetailAction({ id: ID })).toEqual(forbidden);
    expect(
      await actions.createBookingAction({
        date: "2026-10-23",
        time: "10:00",
        party_size: 2,
        contact: { name: "Ana", phone: null },
        idempotencyKey: KEY,
      }),
    ).toEqual(forbidden);
    expect(h.backend.reservasBooking).not.toHaveBeenCalled();
    expect(h.backend.reservasCreateBooking).not.toHaveBeenCalled();
  });

  it("validates before asking: no write leaves without its key, a name, a real day", async () => {
    h.setClient(["reservas"]);
    await expect(
      actions.createBookingAction({ date: "2026-10-23", time: "10:00", contact: { name: "Ana", phone: null } }),
    ).rejects.toThrow();
    await expect(
      actions.createBookingAction({ date: "2026-10-23", time: "10:00", contact: { name: "   ", phone: null }, idempotencyKey: KEY }),
    ).rejects.toThrow();
    await expect(
      actions.createBookingAction({ date: "23/10/2026", time: "10:00", contact: { name: "Ana", phone: null }, idempotencyKey: KEY }),
    ).rejects.toThrow();
    await expect(actions.moveBookingAction({ id: ID, notify: true })).rejects.toThrow();
    await expect(actions.bookingDetailAction({ id: "not-a-uuid" })).rejects.toThrow();
    await expect(
      actions.createBlockAction({ date: "2026-10-24", from: "22:00", until: "20:00", label: "x", idempotencyKey: KEY }),
    ).rejects.toThrow();
  });
});
