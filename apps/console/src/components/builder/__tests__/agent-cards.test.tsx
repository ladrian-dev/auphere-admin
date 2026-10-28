import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientAgent } from "@/lib/backend";

import { AgentCards } from "../agent-cards";

/**
 * Spec 047 (historia 7, escenario 6; requisito 17.2) — la pestaña Agentes: una
 * tarjeta por agente con si está publicado o solo en borrador y sus canales,
 * que lleva a la pantalla del agente. «Nuevo agente» solo para quien puede
 * crear agentes (§V).
 */

const REF = "barberia-cultor";
const agent = (over: Partial<ClientAgent>): ClientAgent => ({
  id: "11111111-1111-4111-8111-111111111111",
  name: "Recepción",
  status: "active",
  is_principal: true,
  channels: [{ id: "c1", display: "+34 600 000 000" }],
  active_version: 3,
  draft_version: null,
  ...over,
});
const AGENTS: ClientAgent[] = [
  agent({}),
  agent({ id: "22222222-2222-4222-8222-222222222222", name: "Ventas", is_principal: false, channels: [], active_version: null, draft_version: 4 }),
  agent({
    id: "33333333-3333-4333-8333-333333333333",
    name: "Cobros",
    is_principal: false,
    channels: [
      { id: "c2", display: "+34 600 000 001" },
      { id: "c3", display: "+34 600 000 002" },
    ],
    active_version: 2,
    draft_version: 5,
  }),
];

function cards(agents: ClientAgent[] | null, canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <AgentCards refId={REF} agents={agents} canWrite={canWrite} />
    </LocaleProvider>,
  );
}

describe("la pestaña Agentes", () => {
  it("dice de cada agente si está publicado o en borrador y cuántos canales tiene, y pasa axe", async () => {
    const { container } = cards(AGENTS);
    const list = screen.getByRole("list", { name: "Agentes del cliente" });
    const [recepcion, ventas, cobros] = within(list).getAllByRole("link");
    expect(recepcion).toHaveAttribute("href", `/clients/${REF}/agents/11111111-1111-4111-8111-111111111111`);
    expect(within(recepcion!).getByText("Publicado")).toBeVisible();
    expect(within(recepcion!).getByText("1 canal")).toBeVisible();
    expect(within(recepcion!).getByText("Por defecto")).toBeVisible();
    expect(within(ventas!).getByText("Borrador")).toBeVisible();
    expect(within(ventas!).getByText("Sin canal")).toBeVisible();
    expect(within(cobros!).getByText("Con cambios sin publicar")).toBeVisible();
    expect(within(cobros!).getByText("2 canales")).toBeVisible();
    // Un solo botón primario por vista: «Nuevo agente» está en la cabecera del cliente (Andrés, 2026-10-28).
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin agentes, el vacío lo dice (el botón está en la cabecera); sin permiso, solo lo dice", async () => {
    const { container, unmount } = cards([]);
    expect(screen.getByText("Este cliente aún no tiene agentes")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
    unmount();
    cards([], false);
    expect(screen.getByText("Cuando alguien de tu equipo cree uno, aparecerá aquí.")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Nuevo agente" })).toBeNull();
  });

  it("con el estado visible de la API: el mismo texto en todas partes, y abre la pestaña que le toca (25.5, 26.1)", () => {
    cards([
      agent({ name: "Recepción", is_default: true, visible_state: { code: "serving", tone: "positive", reason: null }, opens: "overview" }),
      agent({
        id: "44444444-4444-4444-8444-444444444444",
        name: "Cobros",
        is_principal: false,
        is_default: false,
        visible_state: { code: "paused", tone: "warn", reason: "no_balance" },
        opens: "overview",
      }),
      agent({
        id: "55555555-5555-4555-8555-555555555555",
        name: "Ventas",
        is_principal: false,
        is_default: false,
        visible_state: { code: "ready_no_channel", tone: "info", reason: null },
        opens: "channels",
      }),
    ]);
    const list = screen.getByRole("list", { name: "Agentes del cliente" });
    const [recepcion, cobros, ventas] = within(list).getAllByRole("link");
    expect(within(recepcion!).getByText("Atendiendo")).toBeVisible();
    expect(within(recepcion!).getByText("Por defecto")).toBeVisible();
    expect(within(cobros!).getByText("Pausado · sin saldo")).toBeVisible();
    expect(within(cobros!).queryByText("Por defecto")).toBeNull();
    expect(within(ventas!).getByText("Listo · sin canal")).toBeVisible();
    expect(ventas).toHaveAttribute("href", `/clients/${REF}/channels`);
    expect(cobros).toHaveAttribute("href", `/clients/${REF}/agents/44444444-4444-4444-8444-444444444444`);
  });

  it("si no se pudieron leer, lo dice", () => {
    cards(null);
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos cargar los agentes");
  });
});
