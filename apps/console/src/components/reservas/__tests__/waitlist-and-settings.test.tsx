import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReservasData } from "../context";
import {
  BARBA,
  CORTE,
  LUCIA,
  MARCOS,
  capacitySettings,
  fichaHours,
  offer,
  service,
  servicesSettings,
  staff,
  waitlistEntry,
} from "../model/__tests__/fixtures";
import { ViewRef, a, renderView, resetMocks, router, toasts } from "./harness";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
vi.mock("@/app/(console)/reservas/templates-actions", async () => (await import("./harness")).a);
vi.mock("next/navigation", async () => (await import("./harness")).navigation);
vi.mock("sonner", async () => (await import("./toasts")).sonner);
ViewRef.current = (await import("../reservas-view")).ReservasView;

function servicesData(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff(), staff({ id: MARCOS, name: "Marcos Ibáñez", hours: { ...staff().effective_hours, saturday: [] } })],
    services: [service(), service({ id: BARBA, name: "Barba", duration_minutes: 30, price: { kind: "none" }, staff: "some", staff_ids: [MARCOS] })],
    bookings: null,
    occupancy: null,
    blocks: null,
    waitlist: {
      enabled: true,
      items: [
        waitlistEntry({
          contact: { name: "Rosa Díaz", phone: "+56933334444" },
          service: { id: CORTE, name: "Corte y barba", duration_minutes: 45 },
          booking_id: "00000000-0000-4000-8000-0000000000c1",
          desired: { date: null, time: null, until: null },
        }),
        waitlistEntry({
          contact: { name: "Tomás Vera", phone: null },
          service: { id: BARBA, name: "Barba", duration_minutes: 30 },
          staff: { id: MARCOS, name: "Marcos Ibáñez" },
          desired: { date: null, time: null, until: "2026-10-26" },
          joined: { kind: "person", name: "Valeria Ríos", at: "2026-10-21T15:00:00Z" },
        }),
      ],
    },
    offers: { running: [offer()], recent: [offer({ status: "closed", filled_booking_id: "x" })] },
    ...o,
  };
}

beforeEach(() => resetMocks());

/** Spec 043 (T025): the waitlist tab, both modes. */
describe("Lista de espera", () => {
  it("Servicios: offers with who has the turn, people with what they want, and «Quitar»", async () => {
    a.removeWaitlistAction.mockResolvedValue({ ok: true, data: null });
    a.stopOfferAction.mockResolvedValue({ ok: true, data: offer({ status: "closed" }) });
    renderView(servicesData(), { url: { tab: "waitlist" } });
    expect(screen.getByRole("link", { name: "Lista de espera (2)" })).toHaveAttribute("aria-current", "page");
    const offers = screen.getByRole("region", { name: "Huecos ofrecidos" });
    expect(within(offers).getByText("Avisando · 2 de 3")).toBeInTheDocument();
    expect(within(offers).getByText("Hueco ocupado")).toBeInTheDocument();
    expect(within(offers).getByText(/Pedro Soto tiene \d:\d\d para responder/)).toBeInTheDocument();
    expect(within(offers).getAllByText("No respondió").length).toBeGreaterThan(0);
    expect(within(offers).getAllByText("Corte y barba con Lucía · cancelada por Ana Pérez").length).toBe(2);
    await userEvent.click(within(offers).getByRole("button", { name: "Detener" }));
    await waitFor(() => expect(a.stopOfferAction).toHaveBeenCalled());
    expect(within(offers).getAllByText("Ver en la agenda")[0]!.closest("a")).toHaveAttribute("href", "/reservas");

    const people = screen.getByRole("region", { name: "Personas en la lista" });
    expect(within(people).getByText("Adelantar su reserva")).toBeInTheDocument();
    expect(within(people).getByText("Cualquier hueco hasta el lun 26")).toBeInTheDocument();
    expect(within(people).getByText("Sin teléfono")).toBeInTheDocument();
    expect(within(people).getByText(/La apuntó Valeria Ríos · ayer/)).toBeInTheDocument();
    await userEvent.click(within(people).getByRole("button", { name: "Quitar a Tomás Vera de la lista" }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Quitado de la lista."));
  });

  it("Servicios: who wants an earlier time says which booking, from `booking_local` (enmienda 2026-10-22)", () => {
    const d = servicesData();
    d.waitlist!.items.push(
      waitlistEntry({
        contact: { name: "Inés Rubio", phone: "+56944445555" },
        service: { id: CORTE, name: "Corte y barba", duration_minutes: 45 },
        booking_id: "00000000-0000-4000-8000-0000000000c2",
        booking_local: { date: "2026-10-29", start: "12:00", end: "12:45" },
        desired: { date: null, time: null, until: null },
      }),
      waitlistEntry({
        contact: { name: "Luis Mena", phone: "+56955556666" },
        service: { id: CORTE, name: "Corte y barba", duration_minutes: 45 },
        booking_id: "00000000-0000-4000-8000-0000000000c3",
        booking_local: { date: "2026-10-23", start: "10:00", end: "10:45" },
        desired: { date: null, time: null, until: null },
      }),
    );
    renderView(d, { url: { tab: "waitlist" } });
    const people = screen.getByRole("region", { name: "Personas en la lista" });
    expect(within(people).getByText("Adelantar su reserva del jueves 29 a las 12:00")).toBeInTheDocument();
    expect(within(people).getByText("Adelantar su reserva de mañana a las 10:00")).toBeInTheDocument();
    // An entry whose booking the API could not place still says what it wants.
    expect(within(people).getByText("Adelantar su reserva")).toBeInTheDocument();
  });

  it("Servicios: «Apuntar a alguien» — name, optional phone, service, with whom, any opening until a day", async () => {
    a.addWaitlistAction.mockResolvedValue({ ok: true, data: waitlistEntry() });
    renderView(servicesData(), { url: { tab: "waitlist" } });
    const people = screen.getByRole("region", { name: "Personas en la lista" });
    await userEvent.click(within(people).getByRole("button", { name: "Apuntar a alguien" }));
    const dialog = await screen.findByRole("dialog", { name: "Apuntar en la lista de espera" });
    const save = within(dialog).getByRole("button", { name: "Apuntar" });
    // Spec 056 (11.1): like «Nueva reserva», nothing leaves without a name and a
    // service, and the field says so when one leaves it.
    expect(save).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("textbox", { name: /Cliente/ }));
    await userEvent.tab();
    expect(within(dialog).getByText("Escribe el nombre del cliente.")).toBeInTheDocument();
    expect(a.addWaitlistAction).not.toHaveBeenCalled();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Cliente/ }), "Inés Rubio");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Teléfono/ }), "+56 9 4444 5555");
    await userEvent.click(within(dialog).getByRole("button", { name: "Corte y barba · 45 min" }));
    const withWhom = within(dialog).getByRole("group", { name: "Con" });
    expect(within(withWhom).getByRole("button", { name: "Cualquiera", pressed: true })).toBeInTheDocument();
    await userEvent.click(within(withWhom).getByRole("button", { name: "Lucía" }));
    const until = within(dialog).getByLabelText(/Cualquier hueco hasta/);
    expect(until).toHaveValue("2026-10-29");
    expect(until).toHaveAttribute("min", "2026-10-22");
    await userEvent.click(save);
    await waitFor(() =>
      expect(a.addWaitlistAction).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Inés Rubio",
          phone: "+56 9 4444 5555",
          service_id: CORTE,
          staff_id: LUCIA,
          date: null,
          until: "2026-10-29",
          idempotencyKey: expect.any(String),
        }),
      ),
    );
    expect(toasts.success).toHaveBeenCalledWith("Inés Rubio está en la lista de espera.");
    expect(router.refresh).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Apuntar en la lista de espera" })).toBeNull());
  });

  it("Servicios: a service only one person does needs no «Con», and anyone is the default", async () => {
    a.addWaitlistAction.mockResolvedValue({ ok: true, data: waitlistEntry() });
    renderView(servicesData(), { url: { tab: "waitlist" } });
    await userEvent.click(screen.getByRole("button", { name: "Apuntar a alguien" }));
    const dialog = await screen.findByRole("dialog", { name: "Apuntar en la lista de espera" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Cliente/ }), "Tomás Vera");
    await userEvent.click(within(dialog).getByRole("button", { name: "Barba · 30 min" }));
    expect(within(dialog).queryByRole("group", { name: "Con" })).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Apuntar" }));
    await waitFor(() =>
      expect(a.addWaitlistAction).toHaveBeenCalledWith(expect.objectContaining({ name: "Tomás Vera", phone: null, service_id: BARBA, staff_id: null })),
    );
  });

  it("Servicios: a refusal is said inside the form and the same key is kept for the retry", async () => {
    a.addWaitlistAction.mockResolvedValueOnce({ ok: false, status: 0, message: "network" });
    renderView(servicesData(), { url: { tab: "waitlist" } });
    await userEvent.click(screen.getByRole("button", { name: "Apuntar a alguien" }));
    const dialog = await screen.findByRole("dialog", { name: "Apuntar en la lista de espera" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Cliente/ }), "Inés Rubio");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Teléfono/ }), "abc");
    await userEvent.click(within(dialog).getByRole("button", { name: "Corte y barba · 45 min" }));
    expect(within(dialog).getByText("Escribe el teléfono con su código, como +56 9 1234 5678.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Apuntar" })).toBeDisabled();
    expect(a.addWaitlistAction).not.toHaveBeenCalled();
    await userEvent.clear(within(dialog).getByRole("textbox", { name: /Teléfono/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Apuntar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No se pudo hablar con el servidor.");
    a.addWaitlistAction.mockResolvedValueOnce({ ok: true, data: waitlistEntry() });
    await userEvent.click(within(dialog).getByRole("button", { name: "Apuntar" }));
    await waitFor(() => expect(a.addWaitlistAction).toHaveBeenCalledTimes(2));
    const [first, second] = a.addWaitlistAction.mock.calls.map((c) => (c[0] as { idempotencyKey: string }).idempotencyKey);
    expect(second).toBe(first);
  });

  it("closing with something written asks before discarding it (spec 056, 12.3)", async () => {
    renderView(servicesData(), { url: { tab: "waitlist" } });
    await userEvent.click(screen.getByRole("button", { name: "Apuntar a alguien" }));
    const dialog = await screen.findByRole("dialog", { name: "Apuntar en la lista de espera" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Cliente/ }), "Inés");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    const ask = await screen.findByRole("dialog", { name: "¿Descartar lo que escribiste?" });
    await userEvent.click(within(ask).getByRole("button", { name: "Seguir editando" }));
    expect(within(dialog).getByRole("textbox", { name: /Cliente/ })).toHaveValue("Inés");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Apuntar en la lista de espera" })).toBeNull());
  });

  it("off: says what it would do and turns on with its rules in view, with the version read", async () => {
    a.patchSettingsAction.mockResolvedValue({ ok: true, data: servicesSettings({ version: 5 }) });
    renderView(servicesData({ waitlist: { enabled: false, items: [] } }), { url: { tab: "waitlist" } });
    expect(screen.getByText("La lista de espera está apagada")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Activar lista de espera" }));
    const dialog = await screen.findByRole("dialog", { name: "Activar la lista de espera" });
    expect(within(dialog).getByText(/Solo se ofrecen huecos que empiezan en más de 2 h/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Activar lista de espera" }));
    await waitFor(() => expect(a.patchSettingsAction).toHaveBeenCalledWith({ version: 4, patch: { waitlist: { enabled: true } } }));
  });

  it("Aforo: who waits for room, with «Ofrecer» only when it fits", async () => {
    a.offerWaitlistAction.mockResolvedValue({ ok: true, data: offer() });
    renderView(
      {
        ...servicesData(),
        settings: capacitySettings(),
        staff: null,
        services: null,
        offers: null,
        waitlist: {
          enabled: true,
          items: [
            waitlistEntry(),
            waitlistEntry({ contact: { name: "Lía Mora", phone: null }, fits_now: false }),
            waitlistEntry({ contact: { name: "Juan Paz", phone: null }, offer: { id: "o", deadline_at: "2026-10-22T19:52:30Z" } }),
          ],
        },
      },
      { url: { tab: "waitlist" } },
    );
    const table = screen.getByRole("table");
    expect(within(table).getByText("No cabe")).toBeInTheDocument();
    expect(within(table).getByText("Ofrecida · quedan 13 min")).toBeInTheDocument();
    expect(within(table).getAllByRole("button", { name: /^Ofrecer el sitio a/ })).toHaveLength(1);
    await userEvent.click(within(table).getByRole("button", { name: "Ofrecer el sitio a Marta Gil" }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Se lo ofrecimos por WhatsApp."));
  });
});

/** Spec 043 (T025): Ajustes — saved with If-Match, a stale version said and reloaded. */
describe("Ajustes · Servicios", () => {
  it("switches save at once with the version they read; a stale one reloads", async () => {
    a.patchSettingsAction.mockResolvedValueOnce({ ok: false, status: 412, message: "", code: "stale" });
    renderView(servicesData(), { url: { tab: "settings" } });
    await userEvent.click(screen.getByRole("switch", { name: "Recordatorio por WhatsApp 24 horas antes" }));
    await waitFor(() => expect(a.patchSettingsAction).toHaveBeenCalledWith({ version: 4, patch: { reminder_enabled: false } }));
    expect(toasts.error).toHaveBeenCalledWith("Alguien cambió esto mientras tanto. Te enseñamos lo último.");
    expect(router.refresh).toHaveBeenCalled();
    a.patchSettingsAction.mockResolvedValueOnce({ ok: true, data: servicesSettings({ version: 5 }) });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Antelación mínima para avisar" }), "240");
    await waitFor(() => expect(a.patchSettingsAction).toHaveBeenLastCalledWith({ version: 4, patch: { waitlist: { lead_minutes: 240 } } }));
  });

  it("business hours (spec 056): the ficha's week, only the touched days, and a 422 said on its day", async () => {
    a.patchBusinessHoursAction.mockResolvedValueOnce({ ok: false, status: 422, message: "", code: "bad_step", info: { field: "open", day: "sun" } });
    renderView(servicesData(), { url: { tab: "settings" } });
    const section = screen.getByRole("region", { name: "Horario del negocio" });
    expect(within(section).getAllByText("09:00 – 14:00 · 15:00 – 19:00")).toHaveLength(5);
    expect(within(section).getByText("10:00 – 14:00")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Editar el horario del negocio" }));
    const dialog = await screen.findByRole("dialog", { name: "Horario del negocio" });
    const save = within(dialog).getByRole("button", { name: "Guardar" });
    // Day by day, with up to six shifts: nothing changed, nothing to save.
    expect(within(dialog).getAllByRole("group")).toHaveLength(7);
    expect(save).toBeDisabled();
    await userEvent.click(within(within(dialog).getByRole("group", { name: "Domingo" })).getByRole("button", { name: "Añadir turno" }));
    await userEvent.click(save);
    await waitFor(() => expect(a.patchBusinessHoursAction).toHaveBeenCalledWith({ revision: 3, days: { sun: [{ open: "09:00", close: "14:00" }] } }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Las horas van en pasos de 5 minutos (Domingo).");
    expect(within(dialog).queryByText("No se pudo hablar con el servidor.")).toBeNull();
    a.patchBusinessHoursAction.mockResolvedValueOnce({ ok: true, data: fichaHours() });
    await userEvent.click(save);
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Horario guardado."));
    expect(router.refresh).toHaveBeenCalled();
  });

  it("business hours (spec 056): someone saved meanwhile, said and reloaded", async () => {
    a.patchBusinessHoursAction.mockResolvedValueOnce({ ok: false, status: 409, message: "", code: "revision_conflict", info: { revision: 4 } });
    renderView(servicesData(), { url: { tab: "settings" } });
    await userEvent.click(screen.getByRole("button", { name: "Editar el horario del negocio" }));
    const dialog = await screen.findByRole("dialog", { name: "Horario del negocio" });
    await userEvent.click(within(within(dialog).getByRole("group", { name: "Domingo" })).getByRole("button", { name: "Añadir turno" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Alguien cambió esto mientras tanto. Te enseñamos lo último.");
    expect(router.refresh).toHaveBeenCalled();
  });

  it("business hours (spec 056): a stored time off the step says «Revísalo», and a location's own hours are only read", async () => {
    const days = { ...fichaHours().days, mon: [{ open: "09:07", close: "14:00", overnight: false }] };
    const settings = servicesSettings({
      hours: fichaHours({ layout: "daily", days }),
      location_hours: [
        { location: { id: "00000000-0000-4000-8000-0000000000d1", name: "Cultor Norte" }, has_own_hours: true, label: "Abrimos lunes de 11:00 a 13:00." },
        { location: { id: "00000000-0000-4000-8000-0000000000d2", name: "Cultor Sur" }, has_own_hours: false, label: null },
      ],
    });
    renderView(servicesData({ settings }), { url: { tab: "settings" } });
    const section = screen.getByRole("region", { name: "Horario del negocio" });
    expect(within(section).getByText("09:07 – 14:00")).toBeInTheDocument();
    expect(within(section).getByText("Revísalo")).toBeInTheDocument();
    expect(within(section).getByText("Cultor Norte · Horario propio: Abrimos lunes de 11:00 a 13:00.")).toBeInTheDocument();
    expect(within(section).getByText("Cultor Sur · Usa el horario del negocio")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Editar el horario del negocio" }));
    const dialog = await screen.findByRole("dialog", { name: "Horario del negocio" });
    expect(within(within(dialog).getByRole("group", { name: /Lunes/ })).getByText("Revísalo")).toBeInTheDocument();
    expect(within(dialog).getByText(/El horario propio de una sede lo cambia quien gestiona tus agentes/)).toBeInTheDocument();
    // Changing another day keeps Monday as it is: only Tuesday travels.
    await userEvent.click(within(within(dialog).getByRole("group", { name: "Martes" })).getByRole("button", { name: "Quitar el turno 2" }));
    a.patchBusinessHoursAction.mockResolvedValueOnce({ ok: true, data: fichaHours() });
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(a.patchBusinessHoursAction).toHaveBeenCalledWith({ revision: 3, days: { tue: [{ open: "09:00", close: "14:00" }] } }));
  });

  it("business hours (spec 056, 12.3): closing with changes asks before discarding them", async () => {
    renderView(servicesData(), { url: { tab: "settings" } });
    await userEvent.click(screen.getByRole("button", { name: "Editar el horario del negocio" }));
    const dialog = await screen.findByRole("dialog", { name: "Horario del negocio" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Horario del negocio" })).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Editar el horario del negocio" }));
    const again = await screen.findByRole("dialog", { name: "Horario del negocio" });
    await userEvent.click(within(within(again).getByRole("group", { name: "Domingo" })).getByRole("button", { name: "Añadir turno" }));
    await userEvent.click(within(again).getByRole("button", { name: "Cancelar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Horario del negocio" })).toBeNull());
    expect(a.patchBusinessHoursAction).not.toHaveBeenCalled();
  });

  it("team: add with an Idempotency-Key; archiving with live bookings says how many", async () => {
    a.createStaffAction.mockResolvedValue({ ok: true, data: staff() });
    a.archiveStaffAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "live_reservations", info: { count: 3 } });
    renderView(servicesData(), { url: { tab: "settings" } });
    const team = screen.getByRole("region", { name: "Equipo y horarios" });
    expect(within(team).getByText("Horario propio")).toBeInTheDocument();
    await userEvent.click(within(team).getByRole("button", { name: "Añadir persona" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir persona" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Camila");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(a.createStaffAction).toHaveBeenCalledWith(expect.objectContaining({ name: "Camila", email: null, hours: null, idempotencyKey: expect.any(String) })),
    );
    await userEvent.click(within(team).getByRole("button", { name: "Archivar a Lucía" }));
    const confirm = await screen.findByRole("dialog", { name: "¿Archivar a Lucía?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Archivar" }));
    expect(await within(confirm).findByText("Tiene 3 reservas próximas. Muévelas o cancélalas antes de archivar.")).toBeInTheDocument();
    expect(a.archiveStaffAction).toHaveBeenCalledWith({ id: LUCIA });
  });

  it("services: price in CLP, who does it, and a price that is not a number is refused", async () => {
    a.createServiceAction.mockResolvedValue({ ok: true, data: service() });
    renderView(servicesData(), { url: { tab: "settings" } });
    const section = screen.getByRole("region", { name: "Servicios" });
    // Intl writes CLP with no decimals («15.000 CLP» in es, «CLP 15,000» in en).
    expect(within(section).getByText(/45 min · .*15\.000.* · Todo el equipo/)).toBeInTheDocument();
    expect(within(section).getByText(/30 min · Sin precio · Marcos Ibáñez/)).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Color");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Duración" }), "90");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Importe" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Importe/ }), "abc");
    expect(within(dialog).getByText("Escribe el precio solo con números, como 15000.")).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByRole("textbox", { name: /Importe/ }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Importe/ }), "55.000");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Solo algunas personas" }));
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "Lucía" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(a.createServiceAction).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Color", duration_minutes: 90, price: { kind: "amount", amount_minor: 55000 }, staff_ids: [LUCIA] }),
      ),
    );
  });

  it("services (spec 056): none, free or an amount, 5 to 480 minutes, the name fixed, only what changed, a 422 on its field", async () => {
    a.updateServiceAction.mockResolvedValueOnce({ ok: false, status: 422, message: "invalid", code: "amount_too_large", info: { field: "price" } });
    renderView(servicesData(), { url: { tab: "settings" } });
    const section = screen.getByRole("region", { name: "Servicios" });
    await userEvent.click(within(section).getByRole("button", { name: "Editar Corte y barba" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar servicio" });
    expect(within(dialog).getByRole("textbox", { name: /Nombre/ })).toHaveAttribute("readonly");
    expect(within(dialog).getByText("El nombre lo cambia quien gestiona tus agentes.")).toBeInTheDocument();
    const lengths = within(within(dialog).getByRole("combobox", { name: "Duración" }))
      .getAllByRole("option")
      .map((o) => Number((o as HTMLOptionElement).value));
    expect([lengths[0], lengths.at(-1), lengths.length]).toEqual([5, 480, 96]);
    for (const kind of ["Sin precio", "Gratis", "Importe"]) expect(within(dialog).getByRole("radio", { name: kind })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: "Importe" })).toBeChecked();
    const amount = within(dialog).getByRole("textbox", { name: /Importe/ });
    expect(amount).toHaveValue("15000");
    await userEvent.clear(amount);
    await userEvent.type(amount, "20000");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(a.updateServiceAction).toHaveBeenCalledWith({ id: CORTE, price: { kind: "amount", amount_minor: 20000 } }));
    expect(await within(dialog).findByText("El importe pasa del máximo permitido.")).toBeInTheDocument();
    expect(within(dialog).queryByText("No se pudo hablar con el servidor.")).toBeNull();

    a.updateServiceAction.mockResolvedValueOnce({ ok: true, data: service({ price: { kind: "free" } }) });
    await userEvent.click(within(dialog).getByRole("radio", { name: "Gratis" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(a.updateServiceAction).toHaveBeenLastCalledWith({ id: CORTE, price: { kind: "free" } }));
  });

  it("services (spec 056): an amount above the cap is said before asking", async () => {
    renderView(servicesData(), { url: { tab: "settings" } });
    await userEvent.click(screen.getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Boda");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Importe" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Importe/ }), "1000000000001");
    expect(within(dialog).getByText("El importe pasa del máximo permitido.")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(a.createServiceAction).not.toHaveBeenCalled();
  });

  it("services and team (spec 056, 12.3): closing with changes asks; untouched, it closes at once", async () => {
    renderView(servicesData(), { url: { tab: "settings" } });
    await userEvent.click(screen.getByRole("button", { name: "Editar Corte y barba" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Editar servicio" })).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Editar servicio" })).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Editar Corte y barba" }));
    const svc = await screen.findByRole("dialog", { name: "Editar servicio" });
    await userEvent.click(within(svc).getByRole("radio", { name: "Gratis" }));
    await userEvent.click(within(svc).getByRole("button", { name: "Cancelar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Editar servicio" })).toBeNull());
    expect(a.updateServiceAction).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Añadir persona" }));
    const person = await screen.findByRole("dialog", { name: "Añadir persona" });
    await userEvent.type(within(person).getByRole("textbox", { name: /Nombre/ }), "Camila");
    await userEvent.click(within(person).getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByRole("dialog", { name: "¿Descartar lo que escribiste?" })).toBeInTheDocument();
  });

  it("team (spec 056, 11.3): the e-mail takes up to 254 characters", async () => {
    renderView(servicesData(), { url: { tab: "settings" } });
    await userEvent.click(screen.getByRole("button", { name: "Añadir persona" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir persona" });
    expect(within(dialog).getByRole("textbox", { name: /Correo/ })).toHaveAttribute("maxlength", "254");
  });
});

describe("Ajustes · Aforo", () => {
  function capacityData(): ReservasData {
    return {
      ...servicesData(),
      settings: capacitySettings(),
      staff: null,
      services: null,
      offers: null,
      blocks: [{ id: "00000000-0000-4000-8000-00000000bb02", date: "2026-10-24", from: "20:00", until: "22:00", label: "Cena de empresa", created_by_name: "Valeria Ríos" }],
    };
  }

  it("says who sets the mode, and saves the numbers together", async () => {
    a.patchSettingsAction.mockResolvedValue({ ok: true, data: capacitySettings({ version: 5 }) });
    renderView(capacityData(), { url: { tab: "settings" } });
    expect(screen.getByText(/Modo de reservas: aforo\. Se reserva por número de comensales/)).toBeInTheDocument();
    expect(screen.getByText(/pídenos el modo servicios/)).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Aforo" });
    expect(within(section).getByRole("button", { name: "Guardar" })).toBeDisabled();
    await userEvent.click(within(section).getByRole("button", { name: "Subir Aforo máximo" }));
    await userEvent.selectOptions(within(section).getByRole("combobox", { name: "Tiempo máximo de mesa" }), "120");
    await userEvent.click(within(section).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(a.patchSettingsAction).toHaveBeenCalledWith({
        version: 4,
        patch: { capacity: { seats: 67, stay_minutes: 120, max_party: 10, walkin_hold: 6 } },
      }),
    );
  });

  it("booking hours: shifts editable, refused when they overlap", async () => {
    renderView(capacityData(), { url: { tab: "settings" } });
    const section = screen.getByRole("region", { name: "Horario de reservas" });
    const firsts = within(section).getAllByRole("combobox", { name: "Primera llegada" });
    await userEvent.selectOptions(firsts[1]!, "14:00");
    expect(within(section).getByText(/Revisa las horas/)).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Guardar" })).toBeDisabled();
  });

  it("confirmation by WhatsApp with its moment, «liberar», and upcoming blocks", async () => {
    a.patchSettingsAction.mockResolvedValue({ ok: true, data: capacitySettings({ version: 5 }) });
    renderView(capacityData(), { url: { tab: "settings" } });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Cuándo" }), "same_day_12");
    await waitFor(() => expect(a.patchSettingsAction).toHaveBeenCalledWith({ version: 4, patch: { confirmation: { when: "same_day_12" } } }));
    expect(screen.getByRole("switch", { name: "Liberar si no confirman" })).toBeChecked();
    const blocks = screen.getByRole("region", { name: "Bloqueos y eventos privados" });
    expect(within(blocks).getByText("Sáb 24 · 20:00 – 22:00 · Cena de empresa")).toBeInTheDocument();
    expect(within(blocks).getByText("Lo puso Valeria Ríos")).toBeInTheDocument();
  });
});
