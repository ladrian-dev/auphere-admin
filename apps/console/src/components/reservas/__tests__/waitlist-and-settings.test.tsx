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
  offer,
  service,
  servicesSettings,
  staff,
  waitlistEntry,
} from "../model/__tests__/fixtures";
import { ViewRef, a, renderView, resetMocks, router, toasts } from "./harness";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
vi.mock("next/navigation", async () => (await import("./harness")).navigation);
vi.mock("sonner", async () => (await import("./toasts")).sonner);
ViewRef.current = (await import("../reservas-view")).ReservasView;

function servicesData(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff(), staff({ id: MARCOS, name: "Marcos Ibáñez", hours: { ...staff().effective_hours, saturday: [] } })],
    services: [service(), service({ id: BARBA, name: "Barba", duration_minutes: 30, price: null, staff: "some", staff_ids: [MARCOS] })],
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
    // Nothing leaves without a name and a service.
    await userEvent.click(save);
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
    await userEvent.click(within(dialog).getByRole("button", { name: "Apuntar" }));
    expect(within(dialog).getByText("Escribe el teléfono con su código, como +56 9 1234 5678.")).toBeInTheDocument();
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

  it("business hours: the week to read, and a dialog that saves it", async () => {
    a.putBusinessHoursAction.mockResolvedValue({ ok: true, data: { business_hours: {}, business_hours_label: null } });
    renderView(servicesData(), { url: { tab: "settings" } });
    const section = screen.getByRole("region", { name: "Horario del negocio" });
    expect(within(section).getAllByText("09:00 – 14:00 · 15:00 – 19:00")).toHaveLength(5);
    expect(within(section).getByText("10:00 – 14:00")).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Editar el horario del negocio" }));
    const dialog = await screen.findByRole("dialog", { name: "Horario del negocio" });
    await userEvent.click(within(dialog).getByRole("switch", { name: "Abierto el Domingo" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(a.putBusinessHoursAction).toHaveBeenCalled());
    const sent = a.putBusinessHoursAction.mock.calls[0]![0] as { hours: Record<string, unknown> };
    expect(sent.hours.sunday).toEqual([{ from: "09:00", to: "19:00" }]);
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
    expect(within(section).getByText(/30 min · Sin coste · Marcos Ibáñez/)).toBeInTheDocument();
    await userEvent.click(within(section).getByRole("button", { name: "Añadir servicio" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir servicio" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Color");
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Duración" }), "90");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Precio/ }), "abc");
    expect(within(dialog).getByText("Escribe el precio solo con números, como 15000.")).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByRole("textbox", { name: /Precio/ }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Precio/ }), "55.000");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Solo algunas personas" }));
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "Lucía" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() =>
      expect(a.createServiceAction).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Color", duration_minutes: 90, price_minor: 55000, staff_ids: [LUCIA] }),
      ),
    );
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
