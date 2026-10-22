import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Occupancy, OccupancyDay } from "@/lib/backend/reservas";

import type { ReservasData } from "../context";
import { TODAY, capacityBooking, capacitySettings, detail, occupancyDay, waitlistEntry } from "../model/__tests__/fixtures";
import { ViewRef, a, renderView, resetMocks, router, toasts } from "./harness";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
vi.mock("next/navigation", async () => (await import("./harness")).navigation);
vi.mock("sonner", async () => (await import("./toasts")).sonner);
ViewRef.current = (await import("../reservas-view")).ReservasView;

function day(date: string, mutate: (d: OccupancyDay) => void = () => {}): OccupancyDay {
  const d = occupancyDay(date);
  mutate(d);
  return d;
}

function occupancy(days: OccupancyDay[]): Occupancy {
  return { seats: 64, walkin_hold: 6, stay_minutes: 90, days };
}

const today = day(TODAY, (d) => {
  for (const s of d.slots) s.past = s.time < "16:40";
  d.slots[6]!.present = 40; // 20:30
  d.slots[6]!.arriving = 11;
  d.slots[7]!.present = 60; // 21:00: full for bookings (64 − 6 − 60 < 0)
  d.slots[8]!.blocked = { id: "00000000-0000-4000-8000-00000000bb01", label: "Cena de empresa" };
});

function data(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: capacitySettings(),
    staff: null,
    services: null,
    bookings: {
      items: [
        capacityBooking({ contact: { name: "Familia Rojas", phone: "+56911112222", conversation_id: null }, party_size: 4, note: "Terraza si puede ser" }),
        capacityBooking({
          local: { date: TODAY, start: "20:30", end: "22:00" },
          contact: { name: "Grupo Pérez", phone: null, conversation_id: null },
          party_size: 7,
          status: "pending",
          origin: "person",
          channel: "phone",
          late_minutes: 20,
          allowed: ["arrive", "noshow", "request_confirmation", "move", "cancel"],
        }),
      ],
      closed_days: ["2026-10-26"],
      truncated: false,
    },
    occupancy: occupancy([today]),
    blocks: [{ id: "00000000-0000-4000-8000-00000000bb01", date: TODAY, from: "21:30", until: "21:30", label: "Cena de empresa", created_by_name: "Valeria Ríos" }],
    waitlist: { enabled: true, items: [waitlistEntry({ desired: { date: TODAY, time: "20:30", until: null } })] },
    offers: null,
    ...o,
  };
}

beforeEach(() => resetMocks());

/** Spec 043 (T024): the occupancy map, its levels from tokens, and the hour panel. */
describe("Aforo · map", () => {
  it("says the capacity in the business's words and paints each hour", async () => {
    renderView(data());
    expect(screen.getByText("Aforo 64 comensales · tiempo máximo de mesa 1 h 30 min")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ocupación" })).toHaveAttribute("aria-current", "page");
    const table = screen.getByRole("table", { name: /Ocupación de/ });
    expect(within(table).getByRole("columnheader", { name: "Comida" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Cena" })).toBeInTheDocument();
    expect(within(table).getByRole("button", { name: "jueves, 22 de octubre a las 20:30: 40 de 64 comensales" })).toHaveTextContent("40");
    expect(within(table).getByRole("button", { name: "jueves, 22 de octubre a las 21:00: lleno" })).toHaveTextContent("Lleno");
    expect(within(table).getByRole("button", { name: "jueves, 22 de octubre a las 21:30: bloqueado, Cena de empresa" })).toHaveTextContent("Bloq.");
    expect(within(table).getByRole("button", { name: /a las 13:00: 0 de 64/ })).toHaveClass("opacity-60");
    expect(screen.getByRole("list", { name: "Leyenda" })).toHaveTextContent("menos del 35 %");
  });

  it("the week has a row per day, «–» on closed days", () => {
    renderView(data({ occupancy: occupancy([today, day("2026-10-26", (d) => (d.closed = true))]) }), { url: { period: "week" } });
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row").length).toBe(2 + 7);
    expect(within(table).getAllByText("Cerrado", { exact: false }).length).toBeGreaterThan(0);
  });

  it("the hour panel: people of the hour, what is left, who arrives, who waits", async () => {
    a.offerWaitlistAction.mockResolvedValue({ ok: true, data: {} });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "jueves, 22 de octubre a las 20:30: 40 de 64 comensales" }));
    const panel = await screen.findByRole("dialog", { name: "20:30 · 40 de 64 comensales" });
    expect(within(panel).getByText("Quedan 18 para reservar. Guardas 6 para quien llega sin reserva.")).toBeInTheDocument();
    expect(within(panel).getByText("Llegan a las 20:30 · 2 reservas")).toBeInTheDocument();
    expect(within(panel).getByText("También cuentan 29 comensales que llegaron antes y siguen dentro.")).toBeInTheDocument();
    expect(within(panel).getByText("Lista de espera · 1")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Ofrecer el sitio a Marta Gil" }));
    await waitFor(() => expect(a.offerWaitlistAction).toHaveBeenCalled());
    await userEvent.click(within(panel).getByRole("button", { name: "Reservar a esta hora" }));
    expect(await screen.findByRole("dialog", { name: "Nueva reserva" })).toBeInTheDocument();
  });

  it("a blocked hour offers to unblock it", async () => {
    a.removeBlockAction.mockResolvedValue({ ok: true, data: null });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "jueves, 22 de octubre a las 21:30: bloqueado, Cena de empresa" }));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Bloqueado: Cena de empresa. El agente no acepta reservas a esta hora.")).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Reservar a esta hora" })).toBeNull();
    await userEvent.click(within(panel).getByRole("button", { name: "Desbloquear" }));
    await waitFor(() => expect(a.removeBlockAction).toHaveBeenCalledWith({ id: "00000000-0000-4000-8000-00000000bb01" }));
  });

  it("error: the map that did not load says so, with retry", async () => {
    renderView(data({ occupancy: null }), { errors: ["occupancy"] });
    expect(screen.getByText(/Parte de la información no se pudo cargar/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Reintentar" })[0]!);
    expect(router.refresh).toHaveBeenCalled();
  });
});

/** Spec 043 (T024): the day by hour, with the actions of the service from `allowed`. */
describe("Aforo · list", () => {
  it("groups by arrival and acts inline, optimistically", async () => {
    a.capacitySlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [], first_fit: null } });
    let resolve: (v: unknown) => void = () => {};
    a.bookingTransitionAction.mockReturnValue(new Promise((r) => (resolve = r)));
    renderView(data(), { url: { view: "list" } });
    const group = screen.getByRole("region", { name: "20:30" });
    expect(within(group).getByText("Llegan 2 reservas · 11 comensales")).toBeInTheDocument();
    expect(within(group).getByText("Llega tarde · 20 min")).toBeInTheDocument();
    expect(within(group).getByText("WhatsApp · Terraza si puede ser")).toBeInTheDocument();
    // Only what `allowed` brings: no «Deshacer» here.
    expect(within(group).queryByRole("button", { name: /Deshacer/ })).toBeNull();
    await userEvent.click(within(group).getByRole("button", { name: "Llegó: Grupo Pérez" }));
    // Painted at once: the status is «Llegó» and its buttons are gone while the API answers.
    await waitFor(() => expect(within(group).queryByRole("button", { name: "Llegó: Grupo Pérez" })).toBeNull());
    resolve({ ok: true, data: {} });
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Marcada como llegada."));
    expect(a.bookingTransitionAction).toHaveBeenCalledWith(expect.objectContaining({ action: "arrive" }));
  });

  it("another day's peak: the hour as the figure and the people under it, nothing cut", () => {
    const other = day("2026-10-24", (d) => {
      d.slots[7]!.present = 60; // 21:00
    });
    renderView(data({ occupancy: occupancy([other]) }), { url: { view: "list", period: "day", date: "2026-10-24" } });
    const figures = screen.getByRole("region", { name: "Cifras del periodo" });
    expect(within(figures).getByText("Pico")).toBeInTheDocument();
    expect(within(figures).getByText("21:00")).toBeInTheDocument();
    expect(within(figures).getByText("60 de 64 dentro")).toBeInTheDocument();
  });

  it("the strip narrows the day to one hour and back", async () => {
    a.capacitySlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [], first_fit: null } });
    renderView(data(), { url: { view: "list" } });
    await userEvent.click(screen.getByRole("button", { name: "13:00: 0 de 64. Ver solo esta hora" }));
    expect(screen.getByText("Solo las 13:00")).toBeInTheDocument();
    expect(screen.getByText("No hay reservas este día.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ver todo el día" }));
    expect(screen.getByRole("region", { name: "20:30" })).toBeInTheDocument();
  });

  it("the rail: who waits in the period and the day's blocks, with «Quitar»", async () => {
    a.capacitySlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [], first_fit: null } });
    a.removeBlockAction.mockResolvedValue({ ok: true, data: null });
    renderView(data(), { url: { view: "list" } });
    const rail = screen.getByRole("complementary", { name: "Lo del día" });
    expect(within(rail).getByText("Marta Gil")).toBeInTheDocument();
    await userEvent.click(within(rail).getByRole("button", { name: "Quitar el bloqueo Cena de empresa" }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Bloqueo quitado."));
  });
});

/** Spec 043 (T024): walk-ins against the slot in course. */
describe("Aforo · walk-in", () => {
  const slots = (o: { fits: boolean; left: number; first_fit: string | null }) => ({
    ok: true,
    data: {
      date: TODAY,
      closed: false,
      first_fit: o.first_fit,
      slots: [
        { time: "16:30", shift: "Tarde", fits: o.fits, left: o.left, why: o.fits ? null : "full" },
        { time: "17:00", shift: "Tarde", fits: true, left: 30, why: null },
      ],
    },
  });

  it("fits: says what will be left and registers the arrival", async () => {
    a.capacitySlotsAction.mockResolvedValue(slots({ fits: true, left: 24, first_fit: "16:30" }));
    a.walkinAction.mockResolvedValue({ ok: true, data: capacityBooking() });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Llegada sin reserva" }));
    const dialog = await screen.findByRole("dialog", { name: "Llega alguien sin reserva" });
    expect(await within(dialog).findByText("Cabe. Después quedarán 22 libres hasta las 18:00.")).toBeInTheDocument();
    expect(within(dialog).getByText("Ahora · llegadas de las 16:30 · dentro 40 de 64")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Registrar llegada" }));
    await waitFor(() => expect(a.walkinAction).toHaveBeenCalledWith(expect.objectContaining({ party_size: 2, name: null })));
    expect(toasts.success).toHaveBeenCalledWith("Llegada registrada.");
  });

  it("full: offers the waitlist for the first slot that fits", async () => {
    a.capacitySlotsAction.mockResolvedValue(slots({ fits: false, left: 1, first_fit: "17:00" }));
    a.addWaitlistAction.mockResolvedValue({ ok: true, data: waitlistEntry() });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Llegada sin reserva" }));
    const dialog = await screen.findByRole("dialog", { name: "Llega alguien sin reserva" });
    expect(await within(dialog).findByText("No cabe ahora. Primer hueco para 2 comensales: 17:00.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Luis");
    await userEvent.click(within(dialog).getByRole("button", { name: "Apuntar en lista de espera" }));
    await waitFor(() =>
      expect(a.addWaitlistAction).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Luis", party_size: 2, date: TODAY, time: "17:00", in_person: true }),
      ),
    );
  });
});

/** Spec 043 (T024): new booking by people, and blocking hours. */
describe("Aforo · new booking and blocks", () => {
  it("over the maximum the business is told the agent would not, and can still book", async () => {
    a.capacitySlotsAction.mockResolvedValue({
      ok: true,
      data: {
        date: TODAY,
        closed: false,
        first_fit: "20:00",
        slots: [
          { time: "20:00", shift: "Cena", fits: true, left: 22, why: null },
          { time: "20:30", shift: "Cena", fits: false, left: 2, why: "full" },
        ],
      },
    });
    a.createBookingAction.mockResolvedValue({ ok: true, data: capacityBooking() });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Nueva reserva" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva reserva" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Cumpleaños Soto");
    const more = within(dialog).getByRole("button", { name: "Subir Comensales" });
    for (let i = 0; i < 10; i++) await userEvent.click(more);
    expect(within(dialog).getByText("Más de 10: el agente no acepta reservas así de grandes, pero tú sí puedes hacerla.")).toBeInTheDocument();
    expect(await within(dialog).findByRole("button", { name: "20:30, Completo" })).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("button", { name: "20:00, quedan 22" }));
    expect(within(dialog).getByText("12 comensales · hoy a las 20:00")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar reserva" }));
    await waitFor(() =>
      expect(a.createBookingAction).toHaveBeenCalledWith(
        expect.objectContaining({ date: TODAY, time: "20:00", party_size: 12, contact: { name: "Cumpleaños Soto", phone: null } }),
      ),
    );
  });

  async function openChange(d: ReservasData) {
    const b = d.bookings!.items[0]!;
    a.bookingDetailAction.mockResolvedValue({ ok: true, data: detail({ ...b }) });
    a.capacitySlotsAction.mockResolvedValue({
      ok: true,
      data: { date: TODAY, closed: false, first_fit: "20:30", slots: [{ time: "21:00", shift: "Cena", fits: true, left: 12, why: null }] },
    });
    a.moveBookingAction.mockResolvedValue({ ok: true, data: b });
    renderView(d, { url: { view: "list" } });
    await userEvent.click(screen.getByRole("button", { name: /^Familia Rojas/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Familia Rojas" });
    await userEvent.click(await within(sheet).findByRole("button", { name: "Cambiar" }));
    const dialog = await screen.findByRole("dialog", { name: "Cambiar reserva" });
    await userEvent.click(await within(dialog).findByRole("button", { name: "21:00, quedan 12" }));
    return { dialog, b };
  }

  it("«Cambiar» carries the note: it shows the one there is and sends it when it changes (enmienda 2026-10-22)", async () => {
    const { dialog, b } = await openChange(data());
    const note = within(dialog).getByRole("textbox", { name: /Nota/ });
    expect(note).toHaveValue("Terraza si puede ser");
    await userEvent.clear(note);
    await userEvent.type(note, "Terraza, cumpleaños");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() =>
      expect(a.moveBookingAction).toHaveBeenCalledWith(
        expect.objectContaining({ id: b.id, version: b.version, date: TODAY, time: "21:00", party_size: 4, note: "Terraza, cumpleaños" }),
      ),
    );
  });

  it("«Cambiar» leaves the note alone when it was not touched", async () => {
    const first = await openChange(data());
    await userEvent.click(within(first.dialog).getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(a.moveBookingAction).toHaveBeenCalled());
    expect(a.moveBookingAction.mock.calls[0]![0]).not.toHaveProperty("note");
  });

  it("«Cambiar» with the note emptied sends `null`", async () => {
    const { dialog } = await openChange(data());
    await userEvent.clear(within(dialog).getByRole("textbox", { name: /Nota/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(a.moveBookingAction).toHaveBeenCalledWith(expect.objectContaining({ note: null })));
  });

  it("blocks hours with a reason, and says how many bookings stay", async () => {
    a.capacitySlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [], first_fit: null } });
    a.createBlockAction.mockResolvedValue({ ok: true, data: { block: {}, overlapping_bookings: 3 } });
    renderView(data(), { url: { view: "list" } });
    await userEvent.click(screen.getByRole("button", { name: "Bloquear horas" }));
    const dialog = await screen.findByRole("dialog", { name: "Bloquear horas" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Turno de cena" }));
    expect(within(dialog).getByRole("combobox", { name: "Desde" })).toHaveValue("20:00");
    expect(within(dialog).getByRole("combobox", { name: "Hasta la llegada de las" })).toHaveValue("22:00");
    expect(within(dialog).getByRole("textbox", { name: /Motivo/ })).toHaveValue("Evento privado");
    await userEvent.click(within(dialog).getByRole("button", { name: "Bloquear" }));
    await waitFor(() =>
      expect(a.createBlockAction).toHaveBeenCalledWith(expect.objectContaining({ date: TODAY, from: "20:00", until: "22:00", label: "Evento privado" })),
    );
    expect(toasts.success).toHaveBeenCalledWith(
      "Horas bloqueadas. Ya hay 3 reservas en esas horas: se mantienen, el agente solo deja de aceptar nuevas.",
    );
  });
});
