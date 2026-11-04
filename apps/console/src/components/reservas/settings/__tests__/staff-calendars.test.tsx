import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { ViewRef, a, renderView, resetMocks, router, toasts } from "../../__tests__/harness";
import type { ReservasData } from "../../context";
import { LUCIA, MARCOS, service, servicesSettings, staff } from "../../model/__tests__/fixtures";

const calendar = { account: a.calendarAccountAction, set: a.staffCalendarAction };

vi.mock("@/app/(console)/reservas/actions", async () => (await import("../../__tests__/harness")).a);
vi.mock("next/navigation", async () => (await import("../../__tests__/harness")).navigation);
vi.mock("sonner", async () => (await import("../../__tests__/toasts")).sonner);
ViewRef.current = (await import("../../reservas-view")).ReservasView;

const SECRET = "token=abc123 Reunión con Ana";
const ACCOUNT = {
  provider: "google",
  connected: true,
  connection: "connected",
  unavailable: false,
  calendars: [
    { id: "lucia@agenda", name: "Lucía" },
    { id: "sala@agenda", name: "Sala de arriba" },
  ],
};

function data(o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [
      staff({ calendar: { status: "connected", calendar_name: "Lucía", last_sync_at: "2026-10-22T13:00:00Z", last_error: null } }),
      staff({ id: MARCOS, name: "Marcos Ibáñez" }),
    ],
    services: [service()],
    bookings: null,
    occupancy: null,
    blocks: null,
    waitlist: null,
    offers: null,
    ...o,
  };
}

function open(o: Partial<ReservasData> = {}, locale: "es" | "en" = "es") {
  return renderView(data(o), { url: { tab: "settings" }, locale });
}

const section = (name: string | RegExp = "Calendarios de Google") => screen.getByRole("region", { name });

beforeEach(() => {
  resetMocks();
  calendar.account.mockReset();
  calendar.set.mockReset();
});

describe("Calendarios de Google del equipo", () => {
  it("ideal: cada persona con su calendario, su estado y su última sincronización, y pasa axe", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    open();
    const box = section();
    const lucia = await within(box).findByRole("listitem", { name: "Lucía" });
    expect(within(lucia).getByText(/Sincronizado/)).toBeInTheDocument();
    expect(within(lucia).getByRole("button", { name: "Desconectar el calendario de Lucía" })).toBeInTheDocument();
    const marcos = within(box).getByRole("listitem", { name: "Marcos Ibáñez" });
    expect(within(marcos).getByText("Sin calendario")).toBeInTheDocument();
    expect(within(marcos).queryByRole("button", { name: /Desconectar/ })).toBeNull();
    expect(await axeViolations(box)).toEqual([]);
  });

  it("elegir un calendario lo guarda y vuelve a leer", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    calendar.set.mockResolvedValue({ ok: true, data: staff({ id: MARCOS }) });
    open();
    const select = await within(section()).findByRole("combobox", { name: "Calendario de Marcos Ibáñez" });
    await userEvent.selectOptions(select, "sala@agenda");
    await userEvent.click(screen.getByRole("button", { name: /^Asociar este calendario/ }));
    await waitFor(() => expect(calendar.set).toHaveBeenCalledWith({ id: MARCOS, calendar_id: "sala@agenda" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(toasts.success).toHaveBeenCalled();
  });

  it("desconectar pide confirmación y dice qué pasa con el calendario", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    calendar.set.mockResolvedValue({ ok: true, data: staff() });
    open();
    await userEvent.click(await within(section()).findByRole("button", { name: "Desconectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Desconectar el calendario de Lucía?" });
    expect(within(dialog).getByText(/quitaremos de él los «Ocupado»/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Desconectar" }));
    await waitFor(() => expect(calendar.set).toHaveBeenCalledWith({ id: LUCIA, calendar_id: null }));
  });

  it("un calendario que ya no está en la cuenta se dice junto a la persona", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    calendar.set.mockResolvedValue({ ok: false, status: 422, message: "", code: "unknown_calendar" });
    open();
    const select = await within(section()).findByRole("combobox", { name: "Calendario de Marcos Ibáñez" });
    await userEvent.selectOptions(select, "sala@agenda");
    await userEvent.click(screen.getByRole("button", { name: /^Asociar este calendario/ }));
    const marcos = within(section()).getByRole("listitem", { name: "Marcos Ibáñez" });
    expect(await within(marcos).findByRole("alert")).toHaveTextContent("Ese calendario ya no está en la cuenta conectada.");
  });

  it("cargando: el esqueleto ocupa el sitio de las filas y lo anuncia", () => {
    calendar.account.mockReturnValue(new Promise(() => undefined));
    open();
    expect(within(section()).getByRole("status", { name: "Cargando calendarios" })).toBeInTheDocument();
    expect(within(section()).queryByRole("combobox")).toBeNull();
  });

  it("error: lo dice y deja reintentar, y lo asociado se sigue viendo", async () => {
    calendar.account.mockResolvedValueOnce({ ok: false, status: 500, message: "" });
    calendar.account.mockResolvedValueOnce({ ok: true, data: ACCOUNT });
    open();
    const box = section();
    expect(await within(box).findByText("No pudimos cargar los calendarios.")).toBeInTheDocument();
    expect(within(box).getByRole("listitem", { name: "Lucía" })).toBeInTheDocument();
    expect(within(box).queryByRole("combobox")).toBeNull();
    await userEvent.click(within(box).getByRole("button", { name: "Reintentar" }));
    expect(await within(box).findByRole("combobox", { name: "Calendario de Lucía" })).toBeInTheDocument();
  });

  it("sin conector: lo dice, dice quién lo conecta y no ofrece elegir", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: { ...ACCOUNT, connected: false, connection: "none", calendars: [] } });
    open({ staff: [staff(), staff({ id: MARCOS, name: "Marcos Ibáñez" })] });
    const box = section();
    expect(await within(box).findByText(/Google Calendar no está conectado/)).toBeInTheDocument();
    expect(within(box).getByText(/quien gestiona tus agentes/)).toBeInTheDocument();
    expect(within(box).queryByRole("combobox")).toBeNull();
    expect(within(box).queryByRole("listitem")).toBeNull();
  });

  it("hay que volver a conectar: lo dice, con lo que significa para los huecos", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: { ...ACCOUNT, connected: false, connection: "needs_reauth", calendars: [] } });
    open({
      staff: [staff({ calendar: { status: "needs_reauth", calendar_name: "Lucía", last_sync_at: "2026-10-20T13:00:00Z", last_error: "connection" } })],
    });
    const box = section();
    expect(await within(box).findByText(/Hay que volver a conectar Google Calendar/)).toBeInTheDocument();
    const lucia = within(box).getByRole("listitem", { name: "Lucía" });
    expect(within(lucia).getByText(/no bloquea huecos/)).toBeInTheDocument();
    expect(within(lucia).getByText(/Última sincronización/)).toBeInTheDocument();
    expect(within(lucia).getByRole("button", { name: "Desconectar el calendario de Lucía" })).toBeInTheDocument();
    expect(within(box).queryByRole("combobox")).toBeNull();
    expect(await axeViolations(box)).toEqual([]);
  });

  it("parcial: Google no responde; lo asociado se ve y se puede soltar, pero no elegir", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: { ...ACCOUNT, unavailable: true, calendars: [] } });
    open();
    const box = section();
    expect(await within(box).findByText(/Google no responde/)).toBeInTheDocument();
    expect(within(box).getByRole("button", { name: "Desconectar el calendario de Lucía" })).toBeInTheDocument();
    expect(within(box).queryByRole("combobox")).toBeNull();
    expect(within(box).queryByText(/no tiene calendarios/)).toBeNull();
  });

  it("parcial: sin el equipo, esta parte lo dice en vez de enseñar un equipo vacío", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    open({ staff: null });
    expect(await within(section()).findByText("No pudimos cargar esta parte.")).toBeInTheDocument();
  });

  it("vacío: sin nadie en el equipo, y una cuenta sin calendarios en los que escribir", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: { ...ACCOUNT, calendars: [] } });
    open();
    expect(await within(section()).findByText(/no tiene calendarios en los que se pueda escribir/)).toBeInTheDocument();
    expect(within(section()).queryByRole("combobox")).toBeNull();
  });

  it("vacío: sin nadie en el equipo lo pide", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    open({ staff: [] });
    expect(await within(section()).findByText(/Añade a alguien al equipo/)).toBeInTheDocument();
  });

  it.each([
    ["read", /No pudimos leer su calendario/],
    ["write", /No pudimos escribir todas sus reservas/],
    ["calendar_gone", /ya no existe o no se puede usar/],
    [SECRET, /No pudimos sincronizar su calendario/],
  ])("el error %s sale con una frase nuestra", async (code, sentence) => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    open({ staff: [staff({ calendar: { status: "error", calendar_name: "Lucía", last_sync_at: null, last_error: code } })] });
    const lucia = await within(section()).findByRole("listitem", { name: "Lucía" });
    expect(within(lucia).getByText(sentence)).toBeInTheDocument();
    expect(lucia).not.toHaveTextContent("abc123");
  });

  it("la primera sincronización se dice mientras no ha pasado", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    open({ staff: [staff({ calendar: { status: "connected", calendar_name: "Lucía", last_sync_at: null, last_error: null } })] });
    const lucia = await within(section()).findByRole("listitem", { name: "Lucía" });
    expect(within(lucia).getByText(/Primera sincronización en curso/)).toBeInTheDocument();
  });

  it("en inglés", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: { ...ACCOUNT, connected: false, connection: "none", calendars: [] } });
    open({}, "en");
    const box = section("Google calendars");
    expect(await within(box).findByText(/Google Calendar isn't connected/)).toBeInTheDocument();
  });

  it("ya no promete el calendario «más adelante»", async () => {
    calendar.account.mockResolvedValue({ ok: true, data: ACCOUNT });
    open();
    const team = screen.getByRole("region", { name: "Equipo y horarios" });
    await userEvent.click(within(team).getByRole("button", { name: "Añadir persona" }));
    const dialog = await screen.findByRole("dialog", { name: "Añadir persona" });
    expect(within(dialog).queryByText(/Más adelante/)).toBeNull();
  });
});
