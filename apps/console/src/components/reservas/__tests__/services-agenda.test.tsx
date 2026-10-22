import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ReservasData } from "../context";
import {
  BARBA,
  CORTE,
  LUCIA,
  MARCOS,
  TODAY,
  booking,
  detail,
  offer,
  service,
  servicesSettings,
  staff,
  weekHours,
} from "../model/__tests__/fixtures";
import { ViewRef, a, renderView, resetMocks, router, toasts } from "./harness";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("./harness")).a);
vi.mock("next/navigation", async () => (await import("./harness")).navigation);
vi.mock("sonner", async () => (await import("./toasts")).sonner);
ViewRef.current = (await import("../reservas-view")).ReservasView;

function data(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff(), staff({ id: MARCOS, name: "Marcos Ibáñez", position: 2, effective_hours: weekHours({ thursday: [] }) })],
    services: [service(), service({ id: BARBA, name: "Barba", duration_minutes: 30, price: null })],
    bookings: {
      items: [
        booking({ local: { date: TODAY, start: "10:00", end: "10:45" }, contact: { name: "Ana Pérez", phone: "+56911112222", conversation_id: null } }),
        booking({
          local: { date: TODAY, start: "17:30", end: "18:15" },
          status: "pending",
          origin: "person",
          channel: "phone",
          created_by: { kind: "person", name: "Valeria Ríos" },
          contact: { name: "Pedro Soto", phone: null, conversation_id: null },
        }),
      ],
      closed_days: [],
      truncated: false,
    },
    occupancy: null,
    blocks: null,
    waitlist: { enabled: true, items: [] },
    offers: null,
    ...o,
  };
}

beforeEach(() => resetMocks());

/** Spec 043 (T022/T023): the Agenda of Servicios in its five states. */
describe("Servicios · Agenda", () => {
  it("ideal: a column per professional, pauses, closed days, blocks by status, free cells that book", async () => {
    a.serviceSlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [{ time: "13:00", staff_ids: [LUCIA] }] } });
    renderView(data());
    expect(screen.getByRole("heading", { level: 1, name: "Reservas" })).toBeInTheDocument();
    const grid = screen.getByRole("region", { name: /Agenda del jueves, 22 de octubre/ });
    const lucia = within(grid).getByRole("group", { name: "Lucía" });
    // Lucía: 9–14 and 15–19, the gap between is «Pausa».
    expect(within(lucia).getByText("Pausa")).toBeInTheDocument();
    // Marcos does not work on Thursdays.
    expect(within(within(grid).getByRole("group", { name: "Marcos Ibáñez" })).getByText("Cerrado")).toBeInTheDocument();
    expect(within(grid).getByText("2 reservas · 17 %")).toBeInTheDocument();
    expect(within(lucia).getByRole("button", { name: /10:00 – 10:45 · Ana Pérez · Corte y barba · Confirmada/ })).toBeInTheDocument();
    expect(within(lucia).getByRole("button", { name: /17:30 – 18:15 · Pedro Soto · Corte y barba · Sin confirmar/ })).toBeInTheDocument();
    // Past cells do not answer: it is 16:40 in Santiago.
    expect(within(lucia).queryByRole("button", { name: "Reservar a las 16:00 con Lucía" })).toBeNull();
    await userEvent.click(within(lucia).getByRole("button", { name: "Reservar a las 18:30 con Lucía" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva reserva" });
    expect(within(dialog).getByRole("button", { name: "Lucía", pressed: true })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Hoy", pressed: true })).toBeInTheDocument();
  });

  it("the toolbar keeps the period and the view apart, and moves through the URL", async () => {
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Semana" }));
    expect(router.push).toHaveBeenLastCalledWith("/reservas?period=week", { scroll: false });
    await userEvent.click(screen.getByRole("button", { name: "Lista" }));
    expect(router.push).toHaveBeenLastCalledWith("/reservas?view=list", { scroll: false });
    await userEvent.click(screen.getByRole("button", { name: "Día siguiente" }));
    expect(router.push).toHaveBeenLastCalledWith("/reservas?date=2026-10-23", { scroll: false });
    expect(screen.getByRole("button", { name: "Hoy" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Persona del equipo" })).toBeInTheDocument();
  });

  it("week: one professional, chosen by chips; month: closed days and a click to the day", async () => {
    const { unmount } = renderView(data(), { url: { period: "week" } });
    const chips = screen.getByRole("group", { name: "Semana de" });
    expect(within(chips).getByRole("button", { name: "Lucía", pressed: true })).toBeInTheDocument();
    await userEvent.click(within(chips).getByRole("button", { name: "Marcos Ibáñez" }));
    expect(router.push).toHaveBeenLastCalledWith(`/reservas?period=week&staff=${MARCOS}`, { scroll: false });
    expect(screen.getAllByRole("button", { name: /^Reservar el / }).length).toBeGreaterThan(0);
    unmount();

    renderView(data(), { url: { period: "month" } });
    const month = screen.getByRole("region", { name: /Octubre de 2026/ });
    expect(within(month).getByRole("button", { name: "domingo, 25 de octubre: cerrado. Abrir el día" })).toBeInTheDocument();
    await userEvent.click(within(month).getByRole("button", { name: /^jueves, 22 de octubre: 2 reservas/ }));
    // Today, by day, is the default: the link is the bare page.
    expect(router.push).toHaveBeenLastCalledWith("/reservas", { scroll: false });
  });

  it("list: grouped by day with today marked, filters, and an empty filter that says so", async () => {
    renderView(data(), { url: { view: "list" } });
    expect(screen.getByRole("heading", { name: "Jueves, 22 de octubre · hoy · 2 reservas" })).toBeInTheDocument();
    expect(screen.getByText("Valeria Ríos")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sin confirmar" }));
    expect(screen.queryByText("Ana Pérez")).toBeNull();
    expect(screen.getByText("Pedro Soto")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Canceladas" }));
    expect(screen.getByText("No hay reservas con estos filtros en estos días.")).toBeInTheDocument();
  });

  it("empty: without a team or services it shows how to start, and nothing can be booked", () => {
    renderView(data({ staff: [] }));
    expect(screen.getByRole("heading", { name: "Para empezar, prepara tu agenda" })).toBeInTheDocument();
    expect(screen.getByText("Ir a Ajustes").closest("a")).toHaveAttribute("href", "/reservas?tab=settings");
    expect(screen.getByRole("button", { name: "Nueva reserva" })).toBeDisabled();
  });

  it("error and partial: no settings is an error; a part that failed is said, the rest is painted", async () => {
    const { unmount } = renderView(null);
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar Reservas");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(router.refresh).toHaveBeenCalled();
    unmount();

    renderView(data({ bookings: null }), { errors: ["bookings"] });
    expect(screen.getByText(/Parte de la información no se pudo cargar/)).toBeInTheDocument();
    expect(screen.getAllByText("No pudimos cargar Reservas").length).toBeGreaterThan(0);
  });

  it("a business without hours is told to set them", () => {
    renderView(data({ settings: servicesSettings({ hours_missing: true }) }));
    expect(screen.getByText("Falta el horario del negocio")).toBeInTheDocument();
    expect(screen.getByText("Poner el horario").closest("a")).toHaveAttribute("href", "/reservas?tab=settings");
  });

  it("English: the same screen, in English", () => {
    renderView(data(), { locale: "en" });
    expect(screen.getByRole("heading", { level: 1, name: "Bookings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Schedule" })).toHaveAttribute("aria-current", "page");
  });
});

/** Spec 043 (T023, design §3.1): a slot being offered to the waitlist is held on the grid, dashed. */
describe("Servicios · hueco en oferta", () => {
  const held = (o: Parameters<typeof offer>[0] = {}) =>
    offer({ ...o, slot: { ...offer().slot, local: { date: TODAY, start: "18:15", end: "19:00" }, ...o.slot } });

  it("draws «Ofreciendo el hueco · Lista de espera · i de n» where the slot is, and the cell is not free", () => {
    renderView(data({ offers: { running: [held()], recent: [] } }));
    const lucia = within(screen.getByRole("region", { name: /Agenda del jueves/ })).getByRole("group", { name: "Lucía" });
    const block = within(lucia).getByRole("link", { name: /^18:15 – 19:00 · Ofreciendo el hueco · Lista de espera · 2 de 3/ });
    expect(block).toHaveTextContent("Ofreciendo el hueco · Lista de espera · 2 de 3");
    expect(block).toHaveAttribute("href", "/reservas?tab=waitlist");
    expect(block.className).toContain("border-dashed");
    // Held: nobody books on top of it from the grid.
    expect(within(lucia).queryByRole("button", { name: "Reservar a las 18:30 con Lucía" })).toBeNull();
    expect(within(lucia).getByRole("button", { name: "Reservar a las 17:00 con Lucía" })).toBeInTheDocument();
  });

  it("each offer in its professional's column, only that day, only while it runs", () => {
    renderView(
      data({
        offers: {
          running: [
            held({ slot: { ...offer().slot, staff: { id: MARCOS, name: "Marcos Ibáñez" }, local: { date: TODAY, start: "18:15", end: "19:00" } } }),
            held({ slot: { ...offer().slot, local: { date: "2026-10-23", start: "18:15", end: "19:00" } } }),
            held({ status: "filled", filled_booking_id: "x" }),
          ],
          recent: [],
        },
      }),
    );
    const grid = screen.getByRole("region", { name: /Agenda del jueves/ });
    expect(within(within(grid).getByRole("group", { name: "Lucía" })).queryByText(/Ofreciendo el hueco/)).toBeNull();
    expect(within(within(grid).getByRole("group", { name: "Marcos Ibáñez" })).getAllByRole("link", { name: /Ofreciendo el hueco/ })).toHaveLength(1);
  });

  it("the week of a professional holds it on its day too", () => {
    renderView(data({ offers: { running: [held()], recent: [] } }), { url: { period: "week" } });
    expect(screen.getByRole("link", { name: /Ofreciendo el hueco · Lista de espera · 2 de 3/ })).toBeInTheDocument();
  });

  it("without the read of offers the grid is the same as before", () => {
    renderView(data({ offers: null }));
    expect(screen.queryByText(/Ofreciendo el hueco/)).toBeNull();
  });
});

/** Spec 043 (T026): the Panel links to `/reservas?booking={id}`, and the page opens that booking. */
describe("Servicios · abrir una reserva desde el enlace", () => {
  it("opens the booking of the URL, and closing it takes the booking off the URL", async () => {
    const d = data();
    const b = d.bookings!.items[1]!;
    a.bookingDetailAction.mockResolvedValue({ ok: true, data: detail({ ...b, allowed: ["confirm"] }) });
    renderView(d, { booking: b.id });
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Pedro Soto" });
    expect(a.bookingDetailAction).toHaveBeenCalledWith({ id: b.id });
    expect(await within(sheet).findByRole("button", { name: "Marcar confirmada" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Reserva de Pedro Soto" })).toBeNull());
    expect(router.replace).toHaveBeenCalledWith("/reservas", { scroll: false });
  });

  it("a booking that is not in the day's read is still opened by its id", async () => {
    const other = "00000000-0000-4000-8000-00000000e001";
    a.bookingDetailAction.mockResolvedValue({ ok: true, data: detail({ id: other, contact: { name: "Inés Rubio", phone: null, conversation_id: null } }) });
    renderView(data(), { booking: other });
    expect(await screen.findByRole("dialog", { name: "Reserva de Inés Rubio" })).toBeInTheDocument();
    expect(a.bookingDetailAction).toHaveBeenCalledWith({ id: other });
  });
});

/** Spec 043 (T023): the side panel — history in words, buttons only from `allowed`. */
describe("Servicios · detail", () => {
  it("opens with its history and only the allowed buttons; a transition carries the version", async () => {
    const b = data().bookings!.items[1]!;
    a.bookingDetailAction.mockResolvedValue({
      ok: true,
      data: detail({
        ...b,
        wants_earlier: true,
        allowed: ["confirm", "move", "cancel"],
        events: [
          { kind: "created", at: "2026-10-21T13:00:00Z", actor: { kind: "person", name: "Valeria Ríos" }, data: { channel: "phone" } },
          { kind: "notify_failed", at: "2026-10-21T13:01:00Z", actor: { kind: "system", name: null }, data: { why: "no_phone" } },
        ],
      }),
    });
    a.bookingTransitionAction.mockResolvedValue({ ok: true, data: { ...b, status: "confirmed" } });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: /Pedro Soto · Corte y barba · Sin confirmar/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Pedro Soto" });
    await within(sheet).findByText("En lista de espera: quiere adelantar");
    expect(within(sheet).getByText("No se pudo avisar por WhatsApp: no hay teléfono")).toBeInTheDocument();
    expect(within(sheet).getByText("La creó Valeria Ríos · Teléfono")).toBeInTheDocument();
    expect(within(sheet).getByText("La creó Valeria Ríos · Teléfono · ayer 22:14")).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Marcar confirmada" })).toBeInTheDocument();
    expect(within(sheet).queryByRole("button", { name: "No asistió" })).toBeNull();
    expect(within(sheet).queryByRole("button", { name: "Pedir confirmación" })).toBeNull();
    await userEvent.click(within(sheet).getByRole("button", { name: "Marcar confirmada" }));
    await waitFor(() => expect(a.bookingTransitionAction).toHaveBeenCalledWith({ id: b.id, version: b.version, action: "confirm" }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Reserva confirmada."));
    expect(router.refresh).toHaveBeenCalled();
  });

  it("a stale version is told and the screen reads again", async () => {
    const b = data().bookings!.items[1]!;
    a.bookingDetailAction.mockResolvedValue({ ok: true, data: detail({ ...b, allowed: ["confirm"] }) });
    a.bookingTransitionAction.mockResolvedValue({ ok: false, status: 412, message: "", code: "stale" });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: /Pedro Soto/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Pedro Soto" });
    await userEvent.click(await within(sheet).findByRole("button", { name: "Marcar confirmada" }));
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith("Alguien cambió esto mientras tanto. Te enseñamos lo último."));
    expect(router.refresh).toHaveBeenCalled();
  });
});

/** Spec 043 (T023): «Nueva reserva» with real openings, one key per submit, and a taken slot. */
describe("Servicios · new booking", () => {
  async function fillAndPick() {
    a.serviceSlotsAction.mockResolvedValue({
      ok: true,
      data: { date: TODAY, closed: false, slots: [{ time: "18:30", staff_ids: [LUCIA] }, { time: "19:00", staff_ids: [MARCOS] }] },
    });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Nueva reserva" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva reserva" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Cliente/ }), "Rosa Díaz");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Teléfono/ }), "+56 9 3333 4444");
    await userEvent.click(within(dialog).getByRole("button", { name: "Corte y barba · 45 min" }));
    await userEvent.click(await within(dialog).findByRole("button", { name: "18:30" }));
    return dialog;
  }

  it("saves with the slot's professional, joins the waitlist, and retries with the same key", async () => {
    const dialog = await fillAndPick();
    expect(a.serviceSlotsAction).toHaveBeenLastCalledWith({ date: TODAY, service_id: CORTE, staff_id: undefined, exclude: undefined });
    expect(within(dialog).getByText("Hoy · 18:30 – 19:15 · con Lucía")).toBeInTheDocument();
    a.createBookingAction.mockResolvedValueOnce({ ok: false, status: 500, message: "boom" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar reserva" }));
    await within(dialog).findByText("No se pudo hablar con el servidor.");
    const first = a.createBookingAction.mock.calls[0]![0] as { idempotencyKey: string };
    a.createBookingAction.mockResolvedValueOnce({ ok: true, data: booking() });
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar reserva" }));
    await waitFor(() => expect(a.createBookingAction).toHaveBeenCalledTimes(2));
    const second = a.createBookingAction.mock.calls[1]![0] as Record<string, unknown>;
    expect(second.idempotencyKey).toBe(first.idempotencyKey);
    expect(second).toMatchObject({
      date: TODAY,
      time: "18:30",
      staff_id: LUCIA,
      service_id: CORTE,
      contact: { name: "Rosa Díaz", phone: "+56 9 3333 4444" },
      join_waitlist: true,
      notify: true,
    });
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Reserva guardada para hoy a las 18:30."));
  });

  it("a slot taken meanwhile says so and reads the openings again", async () => {
    const dialog = await fillAndPick();
    a.createBookingAction.mockResolvedValueOnce({ ok: false, status: 409, message: "", code: "slot_taken", info: { first_fit: null } });
    const calls = a.serviceSlotsAction.mock.calls.length;
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar reserva" }));
    expect(await within(dialog).findByText("Esa hora se acaba de ocupar. Elige otra.")).toBeInTheDocument();
    await waitFor(() => expect(a.serviceSlotsAction.mock.calls.length).toBeGreaterThan(calls));
    expect(within(dialog).getByText("Elige una hora")).toBeInTheDocument();
  });

  it("no openings that day is said, never an empty row of chips", async () => {
    a.serviceSlotsAction.mockResolvedValue({ ok: true, data: { date: TODAY, closed: false, slots: [] } });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: "Nueva reserva" }));
    const dialog = await screen.findByRole("dialog", { name: "Nueva reserva" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Barba · 30 min" }));
    expect(await within(dialog).findByText("No quedan huecos ese día. Prueba otro día o con otra persona.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Guardar reserva" })).toBeDisabled();
  });
});

/** Spec 043 (T023): cancelling, with the waitlist question when it applies. */
describe("Servicios · cancel", () => {
  async function openCancel() {
    const b = data().bookings!.items[0]!;
    a.bookingDetailAction.mockResolvedValue({ ok: true, data: detail({ ...b, local: { date: "2026-10-23", start: "10:00", end: "10:45" } }) });
    renderView(data());
    await userEvent.click(screen.getByRole("button", { name: /Ana Pérez/ }));
    const sheet = await screen.findByRole("dialog", { name: "Reserva de Ana Pérez" });
    await userEvent.click(await within(sheet).findByRole("button", { name: "Cancelar" }));
    return { dialog: await screen.findByRole("dialog", { name: "Cancelar la reserva" }), b };
  }

  it("offers the slot to the waitlist when the preview says it can", async () => {
    a.cancelPreviewAction.mockResolvedValue({ ok: true, data: { can_offer: true, candidates: 3, why_not: null } });
    a.cancelBookingAction.mockResolvedValue({ ok: true, data: { ...booking(), offer: { id: "o", candidates: 3 } } });
    const { dialog, b } = await openCancel();
    expect(await within(dialog).findByText("¿Quieres que el agente intente llenar el hueco?")).toBeInTheDocument();
    expect(within(dialog).getByText("3 personas encajan. Les escribe de una en una, hasta 5.")).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: "Avisar a Ana por WhatsApp" })).toBeChecked();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar reserva" }));
    await waitFor(() => expect(a.cancelBookingAction).toHaveBeenCalledWith({ id: b.id, version: b.version, notify: true, offer_slot: true }));
    expect(toasts.success).toHaveBeenCalledWith("Reserva cancelada. El agente ofrece el hueco a 3 personas.");
  });

  it("says why not: too soon for the configured lead", async () => {
    a.cancelPreviewAction.mockResolvedValue({ ok: true, data: { can_offer: false, candidates: 0, why_not: "too_soon" } });
    const { dialog } = await openCancel();
    expect(await within(dialog).findByText("Empieza en menos de 2 h: no da tiempo a ofrecerlo a la lista.")).toBeInTheDocument();
    expect(within(dialog).queryByText("¿Quieres que el agente intente llenar el hueco?")).toBeNull();
  });
});
