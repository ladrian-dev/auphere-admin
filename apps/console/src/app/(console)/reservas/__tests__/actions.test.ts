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

const closedWeek = { monday: [], tuesday: [], wednesday: [], thursday: [], friday: [], saturday: [], sunday: [] };

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

  it("hours: up to two ranges a day, in order", async () => {
    h.setClient(["reservas"]);
    const hours = { ...closedWeek, monday: [{ from: "09:00", to: "14:00" }, { from: "15:00", to: "19:00" }] };
    await actions.putBusinessHoursAction({ hours });
    expect(h.backend.reservasPutBusinessHours).toHaveBeenCalledWith(hours);
    await expect(
      actions.putBusinessHoursAction({ hours: { ...closedWeek, monday: [{ from: "14:00", to: "09:00" }] } }),
    ).rejects.toThrow();
    await expect(
      actions.putBusinessHoursAction({
        hours: { ...closedWeek, monday: [{ from: "09:00", to: "14:00" }, { from: "13:00", to: "19:00" }] },
      }),
    ).rejects.toThrow();
  });

  it("team, services, blocks, walk-ins and the waitlist reach their routes", async () => {
    h.setClient(["reservas"]);
    await actions.createStaffAction({ name: "Lucía", email: null, hours: null, idempotencyKey: KEY });
    expect(h.backend.reservasCreateStaff).toHaveBeenCalledWith({ name: "Lucía", email: null, hours: null }, KEY);
    await actions.createServiceAction({ name: "Corte", duration_minutes: 45, price_minor: 15000, staff_ids: null, idempotencyKey: KEY });
    expect(h.backend.reservasCreateService).toHaveBeenCalledWith(
      { name: "Corte", duration_minutes: 45, price_minor: 15000, staff_ids: null },
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
