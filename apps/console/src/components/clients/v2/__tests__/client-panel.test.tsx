import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { USD, bag, panel, serving } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  getClientReadAction: vi.fn(async () => ({ ok: true, data: { job: null, website: null, networks: [] } })),
  startClientReadAction: vi.fn(),
}));

const { ClientPanelView } = await import("../client-panel");
const { periodLabel, spendSegments } = await import("../client-v2-model");

/**
 * Spec 047 (T067, historia 16) con el prototipo aprobado (`clientes.md` §4 y
 * H4): el Panel del cliente en dos columnas. «Saldo» con «Asignar saldo» en su
 * cabecera, lo que queda en grande, lo consumido y lo disponible, la barra
 * apilada contra lo asignado con «Disponible» en la leyenda y los avisos;
 * «Este mes» con tres cifras y el periodo; y a la derecha «Agentes que más
 * consumen» como lista, con el tope todavía editable. Sus estados: ideal, sin
 * agentes, ficha incompleta, 80 % y 100 %, sin ritmo y sin saldo asignado.
 */
const NOW = new Date("2026-10-25T12:00:00Z");
const MONEY = { currency: "USD" as const, canSetCap: false, refillUpTo: null };

function show(p = panel(), money: React.ComponentProps<typeof ClientPanelView>["money"] = MONEY) {
  return render(
    <LocaleProvider locale="es">
      <ClientPanelView panel={p} money={money} now={NOW} />
    </LocaleProvider>,
  );
}

/** El enlace (un botón con forma de enlace) que lleva el texto. */

function card(title: string): HTMLElement {
  return screen.getByRole("region", { name: title });
}

describe("ClientPanelView", () => {
  it("Saldo: lo que queda, lo consumido, lo disponible y la barra contra lo asignado (escenario 1)", async () => {
    const { container } = show();
    // Dos columnas, 1,35 : 1.
    expect(container.querySelector("[data-slot=client-panel-grid]")?.className).toContain("minmax(0,1.35fr)");
    const saldo = card("Saldo");
    expect(within(saldo).getByRole("button", { name: "Asignar saldo" }).querySelector("svg")).toBeTruthy();
    expect(within(saldo).getByText("Quedan")).toBeTruthy();
    expect(saldo.querySelector("[data-slot=panel-left]")?.textContent?.trim()).toMatch(/^6,00\sUSD$/);
    // Los días de la consola se quedan.
    expect(within(saldo).getByText("Unos 4 días al ritmo de los últimos 7 días.")).toBeTruthy();
    expect(within(saldo).getByText(/Consumido/).textContent).toMatch(/^Consumido 10,00\sUSD de 16,00\sUSD · 63 %$/);
    expect(within(saldo).getByText("37 % disponible · saldo compartido por sus agentes")).toBeTruthy();
    // La barra apilada mide contra lo asignado: lo vacío es lo disponible.
    const stack = within(saldo).getByRole("img", { name: /^Consumo por agente sobre el saldo asignado/ });
    const widths = Array.from(stack.children).map((s) => (s as HTMLElement).style.width);
    expect(widths).toEqual(["50%", "12.5%"]);
    expect(stack.getAttribute("aria-label")).toMatch(/Citas: 8,00\sUSD, Ventas: 2,00\sUSD/);
    expect(stack.getAttribute("aria-label")).toMatch(/Disponible: 37 %$/);
    const legend = saldo.querySelector("[data-slot=panel-legend]")!;
    expect(Array.from(legend.children).map((li) => li.textContent)).toEqual(["Citas", "Ventas", "Disponible"]);
    // Sin la insignia de atención en la cabecera.
    expect(saldo.querySelector("[data-slot=status-badge]")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("Este mes: tres cifras y el periodo del día 1 a hoy", () => {
    show();
    const month = card("Este mes");
    expect(within(month).getByText("1–25 oct")).toBeTruthy();
    const figures = within(month)
      .getAllByRole("definition")
      .map((d) => d.textContent);
    expect(figures).toEqual(["5", "60 %", "2"]);
    expect(within(month).getAllByRole("term").map((d) => d.textContent)).toEqual(["Conversaciones", "Resueltas sin persona", "Pasadas a una persona"]);
    expect(within(month).queryByText("Consumo del mes")).toBeNull();
  });

  it("Agentes que más consumen: lista con estado, gasto, barra y su línea, y «Ver todos»", async () => {
    const { container } = show();
    const top = card("Agentes que más consumen");
    expect(within(top).getByRole("link", { name: "Ver todos" }).getAttribute("href")).toBe("/clients/barberia-cultor/agents");
    const items = within(top).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByRole("link", { name: "Citas" }).getAttribute("href")).toBe("/clients/barberia-cultor/agents/a1");
    expect(within(items[0]!).getByText("Atendiendo")).toBeTruthy();
    expect(within(items[0]!).getByText(/^8,00\sUSD$/)).toBeTruthy();
    expect(within(items[0]!).getByText(/^4 conversaciones · 2,00\sUSD por conversación$/)).toBeTruthy();
    expect(within(items[1]!).getByText("Listo · sin canal")).toBeTruthy();
    expect(within(items[1]!).getByText("0 conversaciones")).toBeTruthy();
    // La barra de cada uno, contra el que más gasta.
    const bars = items.map((li) => (li.querySelector("[data-slot=rank-bar]")?.firstElementChild as HTMLElement).style.width);
    expect(bars).toEqual(["100%", "25%"]);
    // Sin tope y sin permiso para ponerlo, no se dice nada.
    expect(within(top).queryByText(/tope/i)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("solo los cuatro que más consumen", () => {
    const one = panel().top_agents[0]!;
    const many = ["a1", "a2", "a3", "a4", "a5"].map((id, i) => ({ ...one, agent_id: id, name: `Agente ${i + 1}`, spent: USD(10 - i) }));
    show(panel({ top_agents: many }));
    expect(within(card("Agentes que más consumen")).getAllByRole("listitem")).toHaveLength(4);
  });

  it("el tope sigue editable desde la línea del agente", () => {
    const [a1, a2] = panel().top_agents;
    show(panel({ top_agents: [{ ...a1!, cap: USD(10) }, a2!] }), { ...MONEY, canSetCap: true });
    const items = within(card("Agentes que más consumen")).getAllByRole("listitem");
    expect(items[0]!.querySelector("[data-slot=rank-sub]")?.textContent).toMatch(/· tope 10,00\sUSD \(80 %\)$/);
    expect(within(items[0]!).getByRole("button", { name: "Cambiar el tope de Citas" }).textContent).toMatch(/10,00\sUSD/);
    // Sin tope, el enlace para ponerlo.
    expect(within(items[1]!).getByRole("button", { name: "Cambiar el tope de Ventas" }).textContent).toBe("Sin tope");
  });

  it("con tope y sin permiso, lo dice sin enlace", () => {
    const [a1] = panel().top_agents;
    show(panel({ top_agents: [{ ...a1!, cap: USD(16) }] }));
    const item = within(card("Agentes que más consumen")).getByRole("listitem");
    expect(item.querySelector("[data-slot=rank-sub]")?.textContent).toMatch(/· tope 16,00\sUSD \(50 %\)$/);
    expect(within(item).queryByRole("button")).toBeNull();
  });

  it("sin agentes, explica qué es uno y ofrece crear el primero (escenario 4)", async () => {
    const { container } = show(panel({ agents_total: 0, top_agents: [], spend_by_agent: [] }));
    expect(
      screen.getByText("Aún no tiene agentes. Un agente atiende un servicio del negocio por un canal, por ejemplo citas por WhatsApp."),
    ).toBeTruthy();
    // Un solo botón primario por vista: «Nuevo agente» ya está en la cabecera del cliente.
    expect(screen.queryByText("Crear el primer agente")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  // Enmienda del 2026-10-29 (T210, requisito 59.7): la tarjeta de lectura vuelve
  // al Panel, arriba a la izquierda, mientras se lee y al terminar. Sustituye la
  // decisión del 2026-10-28 de dejarla solo en Negocio.
  const readJob = (over: Record<string, unknown> = {}) => ({
    job_id: "11111111-1111-4111-8111-111111111111",
    kind: "client_read",
    status: "running",
    agent_id: null,
    progress: { step: "pages", blocks: [{ key: "pages", read: 3 }] },
    questions: null,
    result: null,
    error_code: null,
    created_at: "2026-10-26T10:00:00Z",
    finished_at: null,
    ...over,
  });

  it("la tarjeta de lectura va arriba a la izquierda mientras se lee (59.7)", async () => {
    const { container } = show(panel({ read: { job: readJob(), website: "auphere.com", networks: [] } as never }));
    const card = container.querySelector("[data-slot=client-read-card]");
    expect(card).not.toBeNull();
    // En la columna de Saldo y Este mes, antes de Saldo.
    const left = container.querySelector("[data-slot=panel-balance]")!.parentElement!;
    expect(left.contains(card)).toBe(true);
    expect(left.firstElementChild?.contains(card)).toBe(true);
    expect(screen.getByText("Leyendo auphere.com para completar la ficha: sedes, horario y servicios…")).toBeVisible();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("al terminar sigue: qué se leyó, qué se encontró, qué falta revisar y qué red no se dejó leer (59.4, 59.7)", () => {
    const result = {
      website: "auphere.com",
      sources: [],
      found: { locations: 1, hours: 1, services: 3, policies: 0, faqs: 0, links: 0 },
      applied: 2,
      suggested: 1,
      translated_from: null,
    };
    show(
      panel({
        read: {
          job: readJob({ status: "done", result, finished_at: "2026-10-26T10:02:00Z" }),
          website: "auphere.com",
          networks: [
            { network: "web", status: "read" },
            { network: "instagram", status: "blocked_by_network" },
          ],
        } as never,
      }),
    );
    expect(screen.getByText(/Leímos auphere.com: 1 sede, el horario y 3 servicios/)).toBeVisible();
    expect(screen.getByText("3 datos por revisar en Negocio.")).toBeVisible();
    expect(screen.getByText("Instagram no deja leer perfiles sin cuenta.")).toBeVisible();
    expect(screen.getByText("Revisar").closest("a")).toHaveAttribute("href", "/clients/barberia-cultor/business");
  });

  it("sin lectura no hay tarjeta", () => {
    const { container } = show(panel());
    expect(container.querySelector("[data-slot=client-read-card]")).toBeNull();
  });

  it("no anuncia lo que falta en la ficha: eso se ve en Negocio (Andrés, 2026-10-28)", () => {
    const { container } = show(panel({ missing: { section: "hours", action: "add_hours" } }));
    expect(container.querySelector("[data-slot=panel-missing]")).toBeNull();
    expect(screen.queryByText(/Horarios: falta/)).toBeNull();
    expect(screen.queryByText("Añadir horario")).toBeNull();
  });

  it("sin permiso de escritura no ofrece arreglarlo, y quien no asigna pide saldo", () => {
    show(panel({ missing: { section: "services", action: "add_services" }, allowed: ["request_balance"] }));
    expect(screen.queryByText("Añadir servicios")).toBeNull();
    expect(screen.queryByText("Crear el primer agente")).toBeNull();
    expect(within(card("Saldo")).getByRole("button", { name: "Pedir saldo" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Asignar saldo" })).toBeNull();
  });

  it("avisa en ámbar al 80 % y dice que sin saldo las conversaciones van a la Bandeja (escenario 2)", () => {
    const { rerender } = show(panel({ bag: bag({ pct_spent: 85, pct_left: 15, alerts: ["warn_80"], state: "low" }) }));
    expect(screen.getByText("Queda menos del 20 % del saldo.").tagName).toBe("STRONG");
    expect(screen.getByText(/Al llegar a cero, las conversaciones pasan a la Bandeja/)).toBeTruthy();
    rerender(
      <LocaleProvider locale="es">
        <ClientPanelView
          panel={panel({
            bag: bag({ balance: USD(0), pct_spent: 100, pct_left: 0, alerts: ["empty"], state: "empty", days_left: null, days_estimable: false }),
            attention: { needs: true, reasons: [{ code: "no_balance", count: 1 }] },
          })}
          money={MONEY}
          now={NOW}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(/Sin saldo: las conversaciones pasan a la Bandeja/)).toBeTruthy();
  });

  it("con menos de 3 días de consumo dice que aún no se puede estimar", () => {
    show(panel({ bag: bag({ days_left: null, days_estimable: false }) }));
    expect(screen.getByText("Aún no hay datos para estimarlo.")).toBeTruthy();
  });

  it("sin saldo asignado pinta el bloque igual, con la pista vacía y el aviso rojo", async () => {
    const { container } = show(
      panel({ bag: { ...bag(), state: "unassigned", balance: null, assigned: null, spent: null, pct_spent: null, pct_left: null, days_left: null } }),
    );
    const saldo = card("Saldo");
    expect(saldo.querySelector("[data-slot=panel-left]")?.textContent?.trim()).toMatch(/^0,00\sUSD$/);
    expect(within(saldo).getByText(/Consumido/).textContent).toMatch(/^Consumido 0,00\sUSD de 0,00\sUSD$/);
    expect(within(saldo).getByText("Saldo compartido por sus agentes")).toBeTruthy();
    expect(within(saldo).getByRole("img", { name: /^Consumo por agente sobre el saldo asignado/ }).children).toHaveLength(0);
    expect(saldo.querySelector("[data-slot=panel-legend]")).toBeNull();
    expect(within(saldo).getByText("Sin saldo asignado.").tagName).toBe("STRONG");
    expect(within(saldo).getByText(/Sus agentes pueden crearse y probarse, pero no responderán a clientes reales/)).toBeTruthy();
    expect(within(saldo).queryByText(/bolsa/i)).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("aguanta un nombre de agente largo sin romper la lista", () => {
    const long = "Kundenservice-Terminvereinbarungsassistent Nord";
    show(panel({ top_agents: [{ ...panel().top_agents[0]!, name: long, visible_state: serving }] }));
    const link = screen.getByRole("link", { name: long });
    expect(link.className).toContain("truncate");
    expect(link.getAttribute("title")).toBe(long);
  });
});

describe("el modelo del Panel", () => {
  it("los tramos de la barra reparten lo consumido según el mes y miden contra lo asignado", () => {
    const p = panel();
    expect(spendSegments(p.bag, p.spend_by_agent).map((s) => [s.name, s.pct])).toEqual([
      ["Citas", 50],
      ["Ventas", 12.5],
    ]);
    // Sin saldo asignado, la pista vacía; sin gasto, sin tramos.
    expect(spendSegments({ ...p.bag, state: "unassigned", assigned: null, pct_spent: null }, p.spend_by_agent)).toEqual([]);
    expect(spendSegments(p.bag, [{ agent_id: "x", name: "X", spent: USD(0), share_pct: 0 }])).toEqual([]);
    // Ordenados de más a menos y nunca por encima del 100 %.
    const over = spendSegments(bag({ pct_spent: 140 }), [
      { agent_id: "b", name: "B", spent: USD(1), share_pct: 25 },
      { agent_id: "a", name: "A", spent: USD(3), share_pct: 75 },
    ]);
    expect(over.map((s) => [s.name, s.pct])).toEqual([
      ["A", 75],
      ["B", 25],
    ]);
  });

  it("el periodo va del día 1 a hoy, sin pasar del fin de mes", () => {
    expect(periodLabel("2026-10-01", "2026-10-31", NOW, "es")).toBe("1–25 oct");
    expect(periodLabel("2026-10-01", "2026-10-31", new Date("2026-11-03T00:00:00Z"), "es")).toBe("1–31 oct");
    expect(periodLabel("2026-10-01", "2026-10-31", new Date("2026-10-01T08:00:00Z"), "es")).toBe("1 oct");
  });
});
