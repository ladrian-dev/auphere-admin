import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { USD, bag, panel } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  getClientReadAction: vi.fn(async () => ({ ok: true, data: { job: null, website: null, networks: [] } })),
  startClientReadAction: vi.fn(),
}));

const { ClientPanelView } = await import("../client-panel");

/**
 * Spec 047 (T067, historia 16): el Panel del cliente. Sus estados: ideal, sin
 * agentes (explica y ofrece el primero), con la ficha incompleta (una sola
 * línea con su botón), aviso del 80 % y del 100 %, sin ritmo para estimar los
 * días y sin bolsa asignada. Pasa axe.
 */
function show(p = panel(), canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <ClientPanelView panel={p} canWrite={canWrite} />
    </LocaleProvider>,
  );
}

/** El enlace (un botón con forma de enlace) que lleva el texto. */
function hrefOf(text: string): string | null {
  return screen.getByText(text).closest("a")?.getAttribute("href") ?? null;
}

describe("ClientPanelView", () => {
  it("dice lo que queda, para cuántos días y el reparto por agente (escenario 1)", async () => {
    const { container } = show();
    expect(screen.getByText("Saldo")).toBeTruthy();
    expect(screen.getByText(/^6,00\sUSD$/)).toBeTruthy();
    expect(screen.getByText("Unos 4 días al ritmo de los últimos 7 días.")).toBeTruthy();
    expect(screen.getByText(/Consumido 10,00\sUSD de 16,00\sUSD · 63 %/)).toBeTruthy();
    expect(screen.getByRole("img", { name: /Citas: 8,00\sUSD \(80 %\)/ })).toBeTruthy();
    // El mes, con su periodo.
    expect(screen.getByText("Del 1 oct 2026 al 31 oct 2026")).toBeTruthy();
    expect(screen.getByText("60 %")).toBeTruthy();
    // Los que más consumen, con lo que sale cada conversación y su tope.
    const table = screen.getByRole("region", { name: "Agentes que más consumen" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getByText("Citas")).toBeTruthy();
    expect(within(rows[1]!).getByText(/2,00\sUSD/)).toBeTruthy();
    expect(within(rows[2]!).getByText("Listo · sin canal")).toBeTruthy();
    expect(within(rows[2]!).getAllByText("Sin tope")).toHaveLength(1);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin agentes, explica qué es uno y ofrece crear el primero (escenario 4)", async () => {
    const { container } = show(panel({ agents_total: 0, top_agents: [], spend_by_agent: [] }));
    expect(screen.getByText("Todavía no hay agentes")).toBeTruthy();
    expect(hrefOf("Crear el primer agente")).toBe("/clients/barberia-cultor/agents?new=1");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("una sola línea con lo primero que falta, y su botón (escenario 3)", () => {
    show(panel({ missing: { section: "hours", action: "add_hours" } }));
    expect(screen.getByText("Horarios: falta. Sin horario, los agentes no saben cuándo abrís.")).toBeTruthy();
    expect(hrefOf("Añadir horario")).toBe("/clients/barberia-cultor/business#hours");
  });

  it("sin permiso de escritura no ofrece arreglarlo", () => {
    show(panel({ missing: { section: "services", action: "add_services" }, allowed: ["request_balance"] }), false);
    expect(screen.queryByText("Añadir servicios")).toBeNull();
    expect(screen.queryByText("Crear el primer agente")).toBeNull();
  });

  it("avisa en ámbar al 80 % y dice que sin saldo las conversaciones van a la Bandeja (escenario 2)", () => {
    const { rerender } = show(panel({ bag: bag({ pct_spent: 85, pct_left: 15, alerts: ["warn_80"], state: "low" }) }));
    expect(screen.getByText(/Queda menos del 20 % del saldo/)).toBeTruthy();
    rerender(
      <LocaleProvider locale="es">
        <ClientPanelView
          panel={panel({
            bag: bag({ balance: USD(0), pct_spent: 100, pct_left: 0, alerts: ["empty"], state: "empty", days_left: null, days_estimable: false }),
            attention: { needs: true, reasons: [{ code: "no_balance", count: 1 }] },
          })}
          canWrite
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(/Sin saldo: las conversaciones pasan a la Bandeja/)).toBeTruthy();
    expect(screen.getAllByText("Sin saldo").length).toBeGreaterThan(0);
  });

  it("con menos de 3 días de consumo dice que aún no se puede estimar", () => {
    show(panel({ bag: bag({ days_left: null, days_estimable: false }) }));
    expect(screen.getByText("Aún no hay datos para estimarlo.")).toBeTruthy();
  });

  it("sin bolsa asignada lo dice en lugar de pintar ceros", () => {
    show(panel({ bag: { ...bag(), state: "unassigned", balance: null, assigned: null, spent: null } }));
    expect(screen.getByText("Este cliente aún no tiene bolsa asignada.")).toBeTruthy();
  });

  it("aguanta un nombre de agente largo sin romper la tabla", () => {
    const long = "Kundenservice-Terminvereinbarungsassistent Nord";
    show(panel({ top_agents: [{ ...panel().top_agents[0]!, name: long }] }));
    const cell = screen.getByText(long);
    expect(cell.className).toContain("truncate");
    expect(cell.getAttribute("title")).toBe(long);
  });
});
