import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { ViewRef, a, renderView, resetMocks, router, toasts } from "../../__tests__/harness";
import type { ReservasData } from "../../context";
import { LUCIA, MARCOS, service, servicesSettings, staff } from "../../model/__tests__/fixtures";

vi.mock("@/app/(console)/reservas/actions", async () => (await import("../../__tests__/harness")).a);
vi.mock("next/navigation", async () => (await import("../../__tests__/harness")).navigation);
vi.mock("sonner", async () => (await import("../../__tests__/toasts")).sonner);
ViewRef.current = (await import("../../reservas-view")).ReservasView;

const SECRET = "token=abc123 Reunión con Ana";
const LINK = "https://google.test/auth/ca_1";

type Calendar = NonNullable<Parameters<typeof staff>[0]>["calendar"];

function data(lucia: Calendar, o: Partial<ReservasData> = {}): ReservasData {
  return {
    settings: servicesSettings(),
    staff: [staff({ calendar: lucia }), staff({ id: MARCOS, name: "Marcos Ibáñez" })],
    services: [service()],
    bookings: null,
    occupancy: null,
    blocks: null,
    waitlist: null,
    offers: null,
    ...o,
  };
}

function open(lucia: Calendar = { status: "none" }, o: Partial<ReservasData> = {}, locale: "es" | "en" = "es") {
  return renderView(data(lucia, o), { url: { tab: "settings" }, locale });
}

const section = (name: string | RegExp = "Calendarios de Google") => screen.getByRole("region", { name });
const row = (name = "Lucía") => within(section()).getByRole("listitem", { name });

async function menu(name = "Lucía") {
  await userEvent.click(within(row(name)).getByRole("button", { name: `Más opciones del calendario de ${name}` }));
  return screen.findByRole("menu");
}

const assign = vi.fn();
const writeText = vi.fn();

beforeEach(() => {
  resetMocks();
  assign.mockReset();
  writeText.mockReset();
  writeText.mockResolvedValue(undefined);
  vi.stubGlobal("location", Object.assign(new URL("https://console.test/reservas?tab=settings"), { assign }));
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  a.connectStaffCalendarAction.mockResolvedValue({ ok: true, data: { redirect_url: LINK } });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Calendarios de Google, profesional por profesional", () => {
  it("ideal: cada uno con su estado y una sola acción principal, y pasa axe", async () => {
    open({ status: "connected", calendar_name: "lucia@gmail.com", account: "lucia@gmail.com", last_sync_at: "2026-10-22T13:00:00Z", last_error: null });
    const lucia = row();
    expect(within(lucia).getByText("lucia@gmail.com")).toBeInTheDocument();
    expect(within(lucia).getByText(/Sincronizado/)).toBeInTheDocument();
    expect(within(lucia).queryByRole("button", { name: /^Conectar/ })).toBeNull();
    const marcos = row("Marcos Ibáñez");
    expect(within(marcos).getByText("Sin conectar")).toBeInTheDocument();
    expect(within(marcos).getByRole("button", { name: "Conectar el calendario de Marcos Ibáñez" })).toBeInTheDocument();
    expect(await axeViolations(section())).toEqual([]);
  });

  it("dice qué calendario de la cuenta usa cuando no es el principal", () => {
    open({ status: "connected", calendar_name: "Sala de arriba", account: "lucia@gmail.com", last_sync_at: null, last_error: null });
    expect(within(row()).getByText("lucia@gmail.com · Sala de arriba")).toBeInTheDocument();
    expect(within(row()).getByText(/Primera sincronización/)).toBeInTheDocument();
  });

  it("conectar explica qué se va a hacer y lleva a Google con su propio enlace", async () => {
    open();
    await userEvent.click(within(row()).getByRole("button", { name: "Conectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar el calendario de Lucía" });
    expect(within(dialog).getByText(/sin títulos ni invitados/)).toBeInTheDocument();
    expect(within(dialog).getByText(/como «Ocupado»/)).toBeInTheDocument();
    expect(within(dialog).getByText(/con la cuenta de Lucía/)).toBeInTheDocument();
    expect(await axeViolations(dialog)).toEqual([]);

    await userEvent.click(within(dialog).getByRole("button", { name: "Ir a Google" }));

    await waitFor(() => expect(a.connectStaffCalendarAction).toHaveBeenCalledWith({ id: LUCIA, share: false }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith(LINK));
  });

  it("copiar el enlace deja la fila esperando, para quien no está delante", async () => {
    open();
    await userEvent.click(within(row()).getByRole("button", { name: "Conectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Copiar enlace" }));
    await waitFor(() => expect(a.connectStaffCalendarAction).toHaveBeenCalledWith({ id: LUCIA, share: true }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LINK));
    expect(toasts.success).toHaveBeenCalled();
    expect(router.refresh).toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });

  it("si no se puede copiar, enseña el enlace en vez de decir que se copió", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    open();
    await userEvent.click(within(row()).getByRole("button", { name: "Conectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Copiar enlace" }));
    expect(await within(dialog).findByDisplayValue(LINK)).toBeInTheDocument();
    expect(toasts.success).not.toHaveBeenCalled();
  });

  it("el proveedor caído se dice en el diálogo y no se va a ningún sitio", async () => {
    a.connectStaffCalendarAction.mockResolvedValue({ ok: false, status: 409, message: SECRET, code: "calendar_unavailable" });
    open();
    await userEvent.click(within(row()).getByRole("button", { name: "Conectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Ir a Google" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Google no responde. Inténtalo en un momento.");
    expect(assign).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("abc123");
  });

  it("recién desconectado: dice que espere, no que falló", async () => {
    a.connectStaffCalendarAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "calendar_disconnecting" });
    open();
    await userEvent.click(within(row()).getByRole("button", { name: "Conectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Ir a Google" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/Inténtalo después/);
  });

  it("esperando: «Comprobar» mira cómo quedó", async () => {
    a.refreshStaffCalendarAction.mockResolvedValue({ ok: true, data: staff({ calendar: { status: "connected", calendar_name: "lucia@gmail.com", account: "lucia@gmail.com" } }) });
    open({ status: "pending", calendar_name: null, account: null, last_sync_at: null, last_error: null });
    expect(within(row()).getByText(/Esperando a que autorice/)).toBeInTheDocument();
    await userEvent.click(within(row()).getByRole("button", { name: "Comprobar el calendario de Lucía" }));
    await waitFor(() => expect(a.refreshStaffCalendarAction).toHaveBeenCalledWith({ id: LUCIA }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(toasts.success).toHaveBeenCalled();
  });

  it("permiso perdido: dice qué pasa con los huecos y se resuelve desde la fila", async () => {
    open({ status: "needs_reauth", calendar_name: "lucia@gmail.com", account: "lucia@gmail.com", last_sync_at: "2026-10-22T13:00:00Z", last_error: "auth" });
    expect(within(row()).getByText(/no bloquea huecos/)).toBeInTheDocument();
    expect(within(row()).getByText(/Última sincronización/)).toBeInTheDocument();
    await userEvent.click(within(row()).getByRole("button", { name: "Volver a conectar el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Ir a Google" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith(LINK));
  });

  it("un error que se arregla solo deja reintentar sin esperar", async () => {
    a.refreshStaffCalendarAction.mockResolvedValue({ ok: true, data: staff({ calendar: { status: "error", last_error: "read" } }) });
    open({ status: "error", calendar_name: "lucia@gmail.com", account: "lucia@gmail.com", last_sync_at: null, last_error: "read" });
    expect(within(row()).getByText(/No pudimos leer su calendario/)).toBeInTheDocument();
    await userEvent.click(within(row()).getByRole("button", { name: "Reintentar el calendario de Lucía" }));
    await waitFor(() => expect(a.refreshStaffCalendarAction).toHaveBeenCalledWith({ id: LUCIA }));
    expect(await within(row()).findByRole("alert")).toHaveTextContent(/Sigue sin funcionar/);
  });

  it("un calendario que ya no existe pide elegir otro, y nunca enseña el texto del proveedor", async () => {
    a.staffCalendarsAction.mockResolvedValue({ ok: true, data: { calendars: [{ id: "otro", name: "Otro", primary: false, used_by: null }] } });
    open({ status: "error", calendar_name: "Viejo", account: "lucia@gmail.com", last_sync_at: null, last_error: "calendar_gone" });
    expect(within(row()).getByText(/ya no existe/)).toBeInTheDocument();
    await userEvent.click(within(row()).getByRole("button", { name: "Elegir el calendario de Lucía" }));
    expect(await screen.findByRole("dialog", { name: "Calendario de Lucía" })).toBeInTheDocument();
  });

  it("un código que no conoce la pantalla no se queda sin frase", () => {
    open({ status: "error", calendar_name: "x", account: null, last_sync_at: null, last_error: SECRET });
    expect(within(row()).getByText(/No pudimos sincronizar su calendario/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("abc123");
  });
});

describe("Sin mezclar calendarios", () => {
  it("con la cuenta de otro: lo dice, enseña la cuenta y deja elegir sin pisar a nadie", async () => {
    a.staffCalendarsAction.mockResolvedValue({
      ok: true,
      data: {
        calendars: [
          { id: "marcos@gmail.com", name: "marcos@gmail.com", primary: true, used_by: "Marcos Ibáñez" },
          { id: "sala@group", name: "Sala de arriba", primary: false, used_by: null },
        ],
      },
    });
    a.staffCalendarAction.mockResolvedValue({ ok: true, data: staff() });
    open({ status: "needs_calendar", calendar_name: null, account: "marcos@gmail.com", last_sync_at: null, last_error: "calendar_in_use" });
    expect(within(row()).getByText("marcos@gmail.com")).toBeInTheDocument();
    expect(within(row()).getByText(/ya la usa otra persona/)).toBeInTheDocument();

    await userEvent.click(within(row()).getByRole("button", { name: "Elegir el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog", { name: "Calendario de Lucía" });
    const taken = await within(dialog).findByRole("radio", { name: /marcos@gmail.com/ });
    expect(taken).toBeDisabled();
    expect(within(dialog).getByText("Lo usa Marcos Ibáñez")).toBeInTheDocument();
    expect(await axeViolations(dialog)).toEqual([]);

    await userEvent.click(within(dialog).getByRole("radio", { name: /Sala de arriba/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(a.staffCalendarAction).toHaveBeenCalledWith({ id: LUCIA, calendar_id: "sala@group" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
  });

  it("si otro se lo quedó mientras tanto, lo dice con su nombre", async () => {
    a.staffCalendarsAction.mockResolvedValue({ ok: true, data: { calendars: [{ id: "sala@group", name: "Sala", primary: false, used_by: null }] } });
    a.staffCalendarAction.mockResolvedValue({ ok: false, status: 409, message: "", code: "calendar_in_use", info: { used_by: "Marcos Ibáñez" } });
    open({ status: "needs_calendar", calendar_name: null, account: "x@gmail.com", last_sync_at: null, last_error: null });
    await userEvent.click(within(row()).getByRole("button", { name: "Elegir el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(await within(dialog).findByRole("radio", { name: /Sala/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Ese calendario ya lo usa Marcos Ibáñez.");
  });

  it("una cuenta sin calendarios en los que escribir pide otra", () => {
    open({ status: "needs_calendar", calendar_name: null, account: null, last_sync_at: null, last_error: "no_calendar" });
    expect(within(row()).getByText(/no tiene calendarios en los que se pueda escribir/)).toBeInTheDocument();
    expect(within(row()).getByRole("button", { name: "Conectar otra cuenta para Lucía" })).toBeInTheDocument();
  });

  it("elegir: cargando, error con reintento y vacío", async () => {
    a.staffCalendarsAction.mockReturnValueOnce(new Promise(() => undefined));
    open({ status: "needs_calendar", calendar_name: null, account: "x@gmail.com", last_sync_at: null, last_error: null });
    await userEvent.click(within(row()).getByRole("button", { name: "Elegir el calendario de Lucía" }));
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("status", { name: "Cargando calendarios" })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    a.staffCalendarsAction.mockResolvedValueOnce({ ok: false, status: 409, message: "", code: "calendar_unavailable" });
    await userEvent.click(within(row()).getByRole("button", { name: "Elegir el calendario de Lucía" }));
    dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Google no responde.");

    a.staffCalendarsAction.mockResolvedValueOnce({ ok: true, data: { calendars: [] } });
    await userEvent.click(within(dialog).getByRole("button", { name: "Reintentar" }));
    expect(await within(dialog).findByText(/no tiene calendarios/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Guardar" })).toBeNull();
  });
});

describe("Desconectar", () => {
  it("va en el menú, pide confirmación y dice qué pasa", async () => {
    a.staffCalendarAction.mockResolvedValue({ ok: true, data: staff() });
    open({ status: "connected", calendar_name: "c", account: "c", last_sync_at: null, last_error: null });
    const items = await menu();
    await userEvent.click(within(items).getByRole("menuitem", { name: "Desconectar" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Desconectar el calendario de Lucía?" });
    expect(within(dialog).getByText(/quitaremos de él los «Ocupado»/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Desconectar" }));
    await waitFor(() => expect(a.staffCalendarAction).toHaveBeenCalledWith({ id: LUCIA, calendar_id: null }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
  });

  it("sin conectar no hay menú: no hay nada más que hacer", () => {
    open();
    expect(within(row()).queryByRole("button", { name: /Más opciones/ })).toBeNull();
  });
});

describe("La vuelta de Google", () => {
  function comingBack(status = "success") {
    vi.stubGlobal(
      "location",
      Object.assign(new URL(`https://console.test/reservas?tab=settings&calendar_return=${LUCIA}&status=${status}&connectedAccountId=ca_1`), { assign }),
    );
  }

  it("mira cómo quedó, lo dice una vez y limpia la dirección", async () => {
    comingBack();
    a.refreshStaffCalendarAction.mockResolvedValue({ ok: true, data: staff({ calendar: { status: "connected", calendar_name: "c", account: "c" } }) });
    open({ status: "pending", calendar_name: null, account: null, last_sync_at: null, last_error: null });
    await waitFor(() => expect(a.refreshStaffCalendarAction).toHaveBeenCalledWith({ id: LUCIA }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Calendario de Lucía conectado."));
    expect(router.refresh).toHaveBeenCalled();
    const cleaned = String(router.replace.mock.calls[0]?.[0]);
    expect(cleaned).toContain("tab=settings");
    expect(cleaned).not.toContain("calendar_return");
    expect(cleaned).not.toContain("connectedAccountId");
  });

  it("si Google dice que no terminó, lo dice sin fingir que está conectado", async () => {
    comingBack("failed");
    a.refreshStaffCalendarAction.mockResolvedValue({ ok: true, data: staff({ calendar: { status: "none" } }) });
    open({ status: "pending", calendar_name: null, account: null, last_sync_at: null, last_error: null });
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith("No se completó la conexión del calendario de Lucía."));
    expect(toasts.success).not.toHaveBeenCalled();
  });

  it("una vuelta de alguien que no es del equipo no llama a nadie", async () => {
    vi.stubGlobal("location", Object.assign(new URL("https://console.test/reservas?tab=settings&calendar_return=nope"), { assign }));
    open();
    await new Promise((r) => setTimeout(r, 0));
    expect(a.refreshStaffCalendarAction).not.toHaveBeenCalled();
  });
});

describe("Los otros estados de la sección", () => {
  it("vacío: sin equipo lo dice", () => {
    open({ status: "none" }, { staff: [] });
    expect(within(section()).getByText("Añade a alguien al equipo para conectar su calendario.")).toBeInTheDocument();
  });

  it("error: sin poder leer el equipo no pinta una lista vacía, y se puede reintentar", () => {
    open({ status: "none" }, { staff: null });
    expect(within(section()).getByText(/No pudimos cargar/)).toBeInTheDocument();
    expect(within(section()).getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("si Google no dejó usar la cuenta nueva, lo dice y ofrece otra", () => {
    open({ status: "error", calendar_name: "lucia@gmail.com", account: "lucia@gmail.com", last_sync_at: null, last_error: "new_account_refused" });
    expect(within(row()).getByText(/no dejó usar la cuenta nueva/)).toBeInTheDocument();
    expect(within(row()).queryByRole("button", { name: /Reintentar/ })).toBeNull();
  });

  it("lo que bloquea el Google del negocio se dice en la fila de esa persona", () => {
    open({ status: "none", business_busy: true });
    expect(within(row()).getByText("Sin conectar")).toBeInTheDocument();
    expect(within(row()).getByText(/bloqueadas por el Google del negocio/)).toBeInTheDocument();
  });

  it("elegir: una cuenta que ya no está no se confunde con Google caído", async () => {
    a.staffCalendarsAction.mockResolvedValueOnce({ ok: false, status: 409, message: "", code: "calendar_not_connected" });
    open({ status: "needs_calendar", calendar_name: null, account: "x@gmail.com", last_sync_at: null, last_error: null });
    await userEvent.click(within(row()).getByRole("button", { name: "Elegir el calendario de Lucía" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Esa cuenta ya no está conectada.");
    expect(within(dialog).queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("conectar: mientras quita sus citas no promete minutos", async () => {
    a.connectStaffCalendarAction.mockResolvedValueOnce({ ok: false, status: 409, message: "", code: "calendar_disconnecting" });
    open({ status: "none" });
    await userEvent.click(within(row()).getByRole("button", { name: /Conectar/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Google/ }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("como mucho de una hora");
  });

  it("sin portapapeles el enlace queda a la vista y con su etiqueta", async () => {
    writeText.mockRejectedValueOnce(new Error("denied"));
    open({ status: "none" });
    await userEvent.click(within(row()).getByRole("button", { name: /Conectar/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Copiar/ }));
    const input = await within(dialog).findByLabelText("Enlace para Lucía");
    expect(input).toHaveValue(LINK);
    expect(within(dialog).getByText("Enlace para Lucía").tagName).toBe("LABEL");
  });

  it("en inglés también, y un nombre muy largo no desborda", () => {
    const long = "Donaudampfschifffahrtsgesellschaftskapitänin Wilhelmina";
    open({ status: "none" }, { staff: [staff({ name: long })] }, "en");
    const box = section("Google calendars");
    const person = within(box).getByRole("listitem", { name: long });
    expect(within(person).getByText("Not connected")).toBeInTheDocument();
    expect(within(person).getByText(long).className).toContain("truncate");
    expect(person.className).toContain("min-w-0");
  });
});

describe("Avisos de los datos", () => {
  it("un servicio que no hace nadie o que no cabe se dice en su fila", () => {
    open(
      { status: "none" },
      {
        services: [
          service({ name: "Sin nadie", warnings: ["no_staff"] }),
          service({ id: "s2", name: "Muy largo", warnings: ["does_not_fit"] }),
          service({ id: "s3", name: "Bien" }),
        ],
      },
    );
    const box = section("Servicios");
    expect(within(within(box).getByText("Sin nadie").closest("li")!).getByText(/No lo hace nadie/)).toBeInTheDocument();
    expect(within(within(box).getByText("Muy largo").closest("li")!).getByText(/No cabe en el horario/)).toBeInTheDocument();
    expect(within(box).getByText("Bien").closest("li")!.textContent).not.toMatch(/No lo hace|No cabe/);
  });

  it("alguien con horario propio y ningún día se dice en su fila", () => {
    open({ status: "none" }, { staff: [staff({ warnings: ["no_hours"] })] });
    const box = section(/Equipo/);
    expect(within(box).getByText(/No trabaja ningún día/)).toBeInTheDocument();
  });
});
