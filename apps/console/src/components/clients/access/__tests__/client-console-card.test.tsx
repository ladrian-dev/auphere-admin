import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientAccess } from "@/lib/backend/client-access";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const actions = vi.hoisted(() => ({
  setClientAccessAction: vi.fn(),
  reloadClientAccessAction: vi.fn(),
  inviteClientMemberAction: vi.fn(),
  resendClientMemberAction: vi.fn(),
  revokeClientMemberAction: vi.fn(),
}));
vi.mock("@/app/(console)/clients/[ref]/access/actions", () => actions);

const { ClientConsoleCard } = await import("../client-console-card");

/**
 * Spec 056 (requisito 3.3; D3) — «Consola del cliente»: el interruptor y los
 * módulos Panel, Bandeja, Reservas (con su modo) y Consumo, con las reglas del
 * panel. Agentes y Negocio no se ofrecen (2.3). Y los cinco estados.
 */

function access(over: Partial<ClientAccess> = {}): ClientAccess {
  return { eligible: true, ineligible_reason: null, whatsapp_connected: true, enabled: true, modules: ["panel", "inbox"], members: [], reservas: null, ...over };
}

function Harness({ initial, onRetry = () => {} }: { initial: ClientAccess | null; onRetry?: () => void }) {
  const [a, setA] = React.useState(initial);
  return <ClientConsoleCard refId="flor" access={a} onSaved={setA} onRetry={onRetry} />;
}

function paint(initial: ClientAccess | null = access(), onRetry?: () => void) {
  return render(
    <LocaleProvider locale="es">
      <Harness initial={initial} onRetry={onRetry} />
    </LocaleProvider>,
  );
}

const save = () => screen.getByRole("button", { name: "Guardar" });
const box = (name: RegExp) => screen.getByRole("checkbox", { name });

beforeEach(() => {
  for (const fn of Object.values(actions)) fn.mockReset();
  toast.success.mockClear();
});

describe("Consola del cliente · los módulos (3.3)", () => {
  it("ofrece Panel, Bandeja, Reservas y Consumo, nunca Agentes ni Negocio, y pasa axe", async () => {
    const { container } = paint();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(4);
    for (const [i, name] of [/^Panel/, /^Bandeja de entrada/, /^Reservas/, /^Consumo/].entries()) expect(boxes[i]).toHaveAccessibleName(name);
    expect(screen.queryByRole("checkbox", { name: /Agentes/ })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /Negocio/ })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin cambios no se guarda; al cambiar, manda los módulos en el orden de la barra", async () => {
    const user = userEvent.setup();
    actions.setClientAccessAction.mockResolvedValue({ ok: true, data: access({ modules: ["panel", "inbox", "usage"] }) });
    paint();
    expect(save()).toBeDisabled();
    await user.click(box(/Consumo/));
    await user.click(save());
    await waitFor(() => expect(actions.setClientAccessAction).toHaveBeenCalledWith({ ref: "flor", enabled: true, modules: ["panel", "inbox", "usage"] }));
    expect(toast.success).toHaveBeenCalledWith("Acceso guardado");
  });

  it("encendida exige al menos un módulo", async () => {
    const user = userEvent.setup();
    paint(access({ modules: ["panel"] }));
    await user.click(box(/Panel/));
    expect(screen.getByRole("alert")).toHaveTextContent("Elige al menos una cosa que verá para encender la consola.");
    expect(save()).toBeDisabled();
  });

  it("la Bandeja sin un WhatsApp conectado no se puede elegir, y lo dice", () => {
    paint(access({ whatsapp_connected: false, modules: ["panel"] }));
    expect(box(/Bandeja de entrada/)).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(/Necesita un WhatsApp conectado/)).toBeVisible();
  });

  it("si ya la tenía, la Bandeja no se le quita sola aunque el WhatsApp se haya caído", () => {
    paint(access({ whatsapp_connected: false, modules: ["panel", "inbox"] }));
    expect(box(/Bandeja de entrada/)).not.toHaveAttribute("aria-disabled", "true");
  });

  it("apagar la consola manda `enabled: false` y dice que se cerraron las sesiones", async () => {
    const user = userEvent.setup();
    actions.setClientAccessAction.mockResolvedValue({ ok: true, data: access({ enabled: false }) });
    paint();
    await user.click(screen.getByRole("switch", { name: "Consola encendida" }));
    await user.click(save());
    await waitFor(() => expect(actions.setClientAccessAction).toHaveBeenCalledWith({ ref: "flor", enabled: false, modules: ["panel", "inbox"] }));
    expect(toast.success).toHaveBeenCalledWith("Consola apagada. Se cerraron las sesiones de sus personas");
  });

  it("un no de la API se dice en palabras", async () => {
    const user = userEvent.setup();
    actions.setClientAccessAction.mockResolvedValue({ ok: false, status: 422, message: "inbox requires whatsapp", code: "inbox_requires_whatsapp" });
    paint(access({ modules: ["panel"] }));
    await user.click(box(/Bandeja de entrada/));
    await user.click(save());
    expect(await screen.findByRole("alert")).toHaveTextContent("La Bandeja de entrada necesita un WhatsApp conectado.");
    expect(screen.queryByText("inbox requires whatsapp")).toBeNull();
  });
});

describe("Consola del cliente · Reservas (3.3)", () => {
  it("la primera vez exige el modo, y en Aforo el tipo de negocio", async () => {
    const user = userEvent.setup();
    actions.setClientAccessAction.mockResolvedValue({ ok: true, data: access() });
    paint();
    await user.click(box(/Reservas/));
    expect(screen.getByText("Elige cómo reserva el negocio, Servicios o Aforo.")).toBeVisible();
    expect(save()).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Aforo/ }));
    expect(save()).toBeDisabled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Tipo de negocio" }), "bar");
    expect(save()).toBeEnabled();
    await user.click(save());
    await waitFor(() =>
      expect(actions.setClientAccessAction).toHaveBeenCalledWith({
        ref: "flor",
        enabled: true,
        modules: ["panel", "inbox", "reservas"],
        reservas: { mode: "capacity", capacity_kind: "bar" },
      }),
    );
  });

  it("cambiar el modo con reservas futuras pregunta antes de guardar, y «No cambiar» vuelve al modo guardado", async () => {
    const user = userEvent.setup();
    const stored = access({ modules: ["reservas"], reservas: { mode: "capacity", capacity_kind: "bar", live_future: 3, agents_pending_promotion: [] } });
    paint(stored);
    await user.click(screen.getByRole("radio", { name: /Servicios/ }));
    await user.click(save());
    const dialog = await screen.findByRole("dialog", { name: "¿Cambiar el modo de Reservas?" });
    expect(dialog).toHaveTextContent("Hay 3 reservas futuras. Cambiar de modo las cancela y avisa a cada cliente por WhatsApp.");
    expect(actions.setClientAccessAction).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "No cambiar" }));
    await waitFor(() => expect(screen.getByRole("radio", { name: /Aforo/ })).toBeChecked());
  });

  it("al confirmar, manda `cancel_and_notify`", async () => {
    const user = userEvent.setup();
    const stored = access({ modules: ["reservas"], reservas: { mode: "capacity", capacity_kind: "bar", live_future: 1, agents_pending_promotion: [] } });
    actions.setClientAccessAction.mockResolvedValue({ ok: true, data: access({ modules: ["reservas"], reservas: { mode: "services", capacity_kind: null, live_future: 0, agents_pending_promotion: [] } }) });
    paint(stored);
    await user.click(screen.getByRole("radio", { name: /Servicios/ }));
    await user.click(save());
    const dialog = await screen.findByRole("dialog", { name: "¿Cambiar el modo de Reservas?" });
    expect(dialog).toHaveTextContent("Hay 1 reserva futura.");
    await user.click(within(dialog).getByRole("button", { name: "Cancelarlas y cambiar" }));
    await waitFor(() =>
      expect(actions.setClientAccessAction).toHaveBeenCalledWith({
        ref: "flor",
        enabled: true,
        modules: ["reservas"],
        reservas: { mode: "services", on_live: "cancel_and_notify" },
      }),
    );
    expect(toast.success).toHaveBeenCalledWith("Modo cambiado. Se cancelaron las reservas futuras y se avisa a cada cliente por WhatsApp");
  });

  it("si alguien reservó mientras tanto, la API lo dice y se pregunta con su cuenta", async () => {
    const user = userEvent.setup();
    const stored = access({ modules: ["reservas"], reservas: { mode: "capacity", capacity_kind: "bar", live_future: 0, agents_pending_promotion: [] } });
    actions.setClientAccessAction.mockResolvedValueOnce({ ok: false, status: 409, message: "", code: "live_reservations", info: { count: 2 } });
    paint(stored);
    await user.click(screen.getByRole("radio", { name: /Servicios/ }));
    await user.click(save());
    const dialog = await screen.findByRole("dialog", { name: "¿Cambiar el modo de Reservas?" });
    expect(dialog).toHaveTextContent("Hay 2 reservas futuras.");
  });
});

describe("Consola del cliente · los cinco estados", () => {
  it("vacío: nunca se encendió, y lo dice", () => {
    paint(access({ enabled: false, modules: [] }));
    expect(screen.getByText("Este cliente aún no tiene consola. Enciéndela y elige qué verá.")).toBeVisible();
    expect(screen.getByRole("switch", { name: "Consola encendida" })).not.toBeChecked();
  });

  it("parcial: un cliente archivado se lee y no se cambia", () => {
    paint(access({ eligible: false, ineligible_reason: "archived" }));
    expect(screen.getByText("El cliente está archivado. No se le puede dar acceso.")).toBeVisible();
    expect(screen.getByText(/Tenía la consola encendida con Panel, Bandeja de entrada/)).toBeVisible();
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
  });

  it("error: lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    paint(null, retry);
    expect(screen.getByText("No pudimos leer el acceso de este cliente")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("ideal guardando: el botón dice «Guardando» y no se pulsa dos veces", async () => {
    const user = userEvent.setup();
    let resolve: (v: unknown) => void = () => {};
    actions.setClientAccessAction.mockReturnValue(new Promise((r) => (resolve = r)));
    paint();
    await user.click(box(/Consumo/));
    await user.click(save());
    const busy = await screen.findByRole("button", { name: /Guardando/ });
    expect(busy).toBeDisabled();
    resolve({ ok: true, data: access({ modules: ["panel", "inbox", "usage"] }) });
    await waitFor(() => expect(screen.getByRole("button", { name: "Guardar" })).toBeDisabled());
  });
});
