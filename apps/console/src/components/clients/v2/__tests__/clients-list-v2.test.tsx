import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { USD, bag, noChannel, row, serving } from "./fixtures";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  archiveClientAction: vi.fn(),
  deleteClientV2Action: vi.fn(),
  getClientV2Action: vi.fn(),
  restoreClientAction: vi.fn(),
  updateClientV2Action: vi.fn(),
}));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(),
  nicheSuggestionsAction: vi.fn(),
}));

const { ClientsListV2 } = await import("../clients-list-v2");
const { agentsText, bagBar, filterHref, menuActions, parseFilter, reasonText, stateView } = await import("../client-v2-model");
const { t } = await import("@/i18n/messages");

/**
 * Spec 047 (T065, historia 15) con el prototipo aprobado («Consola de partners
 * v2», `clientes.md` §2 y H6): la lista dice quién necesita algo y por qué. Cubre
 * las columnas (estado con «Al día», agentes en texto con plurales, saldo con su
 * minibarra), el buscador que filtra al escribir, el filtro en un select con sus
 * cuentas, la fila entera clicable, los vacíos dentro de la tabla, el pie, los
 * nombres largos y el menú según el permiso; y pasa axe.
 */
const es = (key: Parameters<typeof t>[1], vars?: Record<string, string | number>) => t("es", key, vars);
const COUNTS = { all: 3, attention: 2, active: 1, archived: 0 };

function list(items = [row()], props: Partial<React.ComponentProps<typeof ClientsListV2>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <ClientsListV2 items={items} counts={COUNTS} filter="all" q="" total={items.length} page={1} limit={50} {...props} />
    </LocaleProvider>,
  );
}

function bodyRows() {
  const table = screen.getByRole("region", { name: "Clientes del partner" });
  return within(table).getAllByRole("row").slice(1);
}

/** La línea bajo la minibarra: «Quedan {x} de {y}» o «Sin saldo asignado». */
function line(r: HTMLElement) {
  return r.querySelector("[data-slot=bag-line]")?.textContent?.trim();
}

/** El relleno de la minibarra de saldo de una fila. */
function fill(r: HTMLElement) {
  const bar = r.querySelector<HTMLElement>("[data-slot=bag-bar]");
  return { bar, fill: bar?.firstElementChild as HTMLElement | null };
}

describe("ClientsListV2", () => {
  beforeEach(() => vi.clearAllMocks());

  it("pinta cada columna como el prototipo: cliente, estado, agentes en texto y saldo con su barra", async () => {
    const { container } = list([
      row({
        external_client_ref: "cafe-origen",
        name: "Café Origen",
        niche: "Cafetería de especialidad",
        agents: [],
        agents_summary: { total: 0, serving: 0, testing: 0, ready_no_channel: 0, draft: 0, paused: 0 },
        attention: { needs: true, reasons: [{ code: "no_balance", count: 1 }] },
        bag: { ...bag(), state: "unassigned", balance: null, assigned: null, spent: null, pct_spent: null, pct_left: null, days_left: null },
      }),
      row({
        external_client_ref: "flor-y-encanto",
        name: "Flor y Encanto",
        niche: "Floristería",
        agents: [
          { agent_id: "r", name: "Recepción", visible_state: serving },
          { agent_id: "v", name: "Ventas mayoristas", visible_state: { code: "testing", tone: "info", pause_reason: null } },
          { agent_id: "c", name: "Cobranza", visible_state: { code: "paused", tone: "warn", pause_reason: "manual" } },
        ],
        agents_summary: { total: 3, serving: 1, testing: 1, ready_no_channel: 0, draft: 0, paused: 1 },
        bag: bag({ balance: USD(17.7), assigned: USD(60), spent: USD(42.3), pct_spent: 70.5, pct_left: 29.5, days_left: 12 }),
      }),
      row({
        external_client_ref: "clinica-sonrisa",
        name: "Clínica Sonrisa",
        attention: { needs: true, reasons: [{ code: "low_balance", count: 1 }] },
        bag: bag({ balance: USD(8), assigned: USD(50), spent: USD(42), pct_spent: 84, pct_left: 16, days_left: 4, state: "low" }),
      }),
      row({
        external_client_ref: "pedidos-ya",
        name: "Pedidos Ya",
        agents: [{ agent_id: "p", name: "Pedidos", visible_state: noChannel }],
        attention: { needs: true, reasons: [{ code: "agent_without_channel", count: 1 }] },
        bag: bag({ balance: USD(0), pct_spent: 100, pct_left: 0, state: "empty", alerts: ["empty"], days_left: null, days_estimable: false }),
      }),
    ]);
    const table = screen.getByRole("region", { name: "Clientes del partner" });
    const head = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(head).toEqual(["Cliente", "Estado", "Agentes", "Saldo", "Acciones"]);
    const rows = bodyRows();
    // El orden es el de la API: no se reordena aquí.
    expect(rows.map((r) => within(r).getAllByRole("link")[0]?.textContent)).toEqual(["Café Origen", "Flor y Encanto", "Clínica Sonrisa", "Pedidos Ya"]);

    // Café Origen: sin saldo asignado, barra roja llena, «Ninguno».
    expect(within(rows[0]!).getByText("Sin saldo")).toBeTruthy();
    expect(within(rows[0]!).getByText("Cafetería de especialidad")).toBeTruthy();
    expect(within(rows[0]!).getByText("Ninguno")).toBeTruthy();
    expect(line(rows[0]!)).toBe("Sin saldo asignado");
    expect(fill(rows[0]!).bar?.dataset.tone).toBe("danger");
    expect(fill(rows[0]!).fill?.style.width).toBe("100%");

    // Flor y Encanto: «Al día», los agentes en texto y lo que queda de lo asignado.
    expect(within(rows[1]!).getByText("Al día")).toBeTruthy();
    expect(within(rows[1]!).getByText("3 agentes · 1 en prueba · 1 pausado")).toBeTruthy();
    expect(line(rows[1]!)).toMatch(/^Quedan 17,70\sUSD de 60,00\sUSD$/);
    expect(within(rows[1]!).getByRole("img", { name: "Ventas mayoristas: En prueba" })).toBeTruthy();
    expect(fill(rows[1]!).fill?.style.width).toBe("70.5%");
    expect(fill(rows[1]!).bar?.dataset.tone).toBe("ok");
    // Los días y el % libre de la consola se quedan en el `title` de la barra.
    expect(fill(rows[1]!).bar?.getAttribute("title")).toBe("12 días · 30 % libre");

    // Clínica: saldo bajo, en ámbar desde el 80 % gastado.
    expect(within(rows[2]!).getByText("Saldo bajo · quedan 4 días")).toBeTruthy();
    expect(fill(rows[2]!).bar?.dataset.tone).toBe("warn");

    // Pedidos: el saldo agotado. El Estado solo dice el estado: lo de los agentes
    // está en su columna (Andrés, 2026-10-28).
    const estado = rows[3]!.querySelectorAll("td")[1] as HTMLElement;
    expect(estado.textContent).not.toMatch(/agente/);
    expect(within(rows[3]!).getByRole("img", { name: "Pedidos: Listo · sin canal" })).toBeTruthy();
    expect(line(rows[3]!)).toMatch(/^Quedan 0,00\sUSD de 200,00\sUSD$/);
    expect(fill(rows[3]!).bar?.dataset.tone).toBe("danger");

    // Sin «Bolsa» en ninguna parte, y el pie del prototipo.
    expect(screen.queryByText(/bolsa/i)).toBeNull();
    expect(screen.getByText("Cada cliente tiene su moneda. El saldo se compara por porcentaje disponible.")).toBeTruthy();
    // La tabla se desplaza dentro de su caja, nunca la página.
    expect(table.className).toContain("overflow-x-auto");
    expect(table.querySelector("table")?.className).toContain("min-w-[760px]");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("el buscador filtra mientras se escribe, sin botón, y conserva el foco", async () => {
    const user = userEvent.setup();
    list([row()], { filter: "attention" });
    expect(screen.queryByRole("button", { name: "Buscar" })).toBeNull();
    const input = screen.getByRole("searchbox", { name: "Buscar clientes" });
    expect(input.getAttribute("placeholder")).toBe("Buscar por nombre o nicho");
    await user.type(input, "dental");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/clients?filter=attention&q=dental", { scroll: false }));
    // Una sola navegación por ráfaga de teclas.
    expect(nav.replace).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(input);
  });

  it("el filtro es un select con la cuenta de cada opción", async () => {
    const user = userEvent.setup();
    const { container } = list([row()], { q: "óptica" });
    const select = screen.getByRole("combobox", { name: "Filtrar clientes" });
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Todos (3)", "Necesitan atención (2)", "Activos (1)", "Archivados (0)"]);
    expect((select as HTMLSelectElement).value).toBe("all");
    await user.selectOptions(select, "archived");
    expect(nav.replace).toHaveBeenCalledWith("/clients?filter=archived&q=%C3%B3ptica", { scroll: false });
    expect(await axeViolations(container)).toEqual([]);
  });

  it("toda la fila abre el cliente, sin quitarle el enlace al nombre", async () => {
    const user = userEvent.setup();
    list([row()]);
    const [first] = bodyRows();
    expect(within(first!).getByRole("link", { name: "Barbería Cultor" }).getAttribute("href")).toBe("/clients/barberia-cultor");
    await user.click(within(first!).getByText("Barbería de barrio"));
    expect(nav.push).toHaveBeenCalledWith("/clients/barberia-cultor");
    nav.push.mockClear();
    // El ⋯ no abre el cliente.
    await user.click(within(first!).getByRole("button", { name: "Acciones de Barbería Cultor" }));
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("la búsqueda sin resultados lo dice dentro de la tabla", async () => {
    const { container } = list([], { q: "dental", counts: { all: 4, attention: 0, active: 4, archived: 0 } });
    expect(screen.getByRole("status").textContent).toBe("Ningún cliente coincide con «dental».");
    expect(screen.getByRole("status").closest("td")?.getAttribute("colspan")).toBe("5");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("un filtro vacío dice «Nada por aquí.»", () => {
    list([], { filter: "archived", counts: { all: 4, attention: 0, active: 4, archived: 0 } });
    expect(screen.getByRole("status").textContent).toBe("Nada por aquí.");
  });

  it("sin clientes invita a crear el primero", () => {
    list([], { counts: { all: 0, attention: 0, active: 0, archived: 0 } });
    expect(screen.getByText("Todavía no hay clientes")).toBeTruthy();
  });

  it("aguanta un nombre y un nicho largos sin partir la fila", () => {
    const name = "Friseursalon Haarschneidekunst und Bartpflege Großstadt";
    list([row({ name, niche: "Herrenfriseur mit Rasurservice und Bartpflegeberatung" })]);
    const link = screen.getByRole("link", { name });
    expect(link.className).toContain("truncate");
    expect(link.getAttribute("title")).toBe(name);
  });

  it("el menú ⋯ trae iconos y solo lo permitido, con «Pedir saldo» para quien no asigna", async () => {
    const user = userEvent.setup();
    list([row({ allowed: ["edit", "request_balance", "new_agent", "archive"] })]);
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    const items = screen.getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Editar cliente", "Pedir saldo", "Archivar"]);
    for (const item of items) expect(item.querySelector("svg")).toBeTruthy();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  it("con todo permitido: editar, asignar, separador, archivar y «Eliminar…»", async () => {
    const user = userEvent.setup();
    list([row()]);
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Editar cliente", "Asignar saldo", "Archivar", "Eliminar…"]);
  });
});

describe("el modelo de la lista", () => {
  it("dice el motivo más grave con su cuenta, y lo demás aparte", () => {
    const view = stateView(
      es,
      "active",
      {
        needs: true,
        reasons: [
          { code: "channel_problem", count: 2 },
          { code: "low_balance", count: 1 },
        ],
      },
      bag({ days_left: 3.6 }),
    );
    expect(view).toEqual({ label: "2 canales con problemas", tone: "danger", more: ["Saldo bajo · quedan 4 días"] });
    expect(stateView(es, "archived", null, null).label).toBe("Archivado");
    expect(stateView(es, "active", { needs: false, reasons: [] }, null)).toEqual({ label: "Al día", tone: "positive", more: [] });
    // Lo de los agentes lo dice su columna: el Estado no lo repite (Andrés, 2026-10-28).
    expect(stateView(es, "active", { needs: true, reasons: [{ code: "agent_without_channel", count: 2 }] }, null)).toEqual({ label: "Al día", tone: "positive", more: [] });
    expect(stateView(es, "active", { needs: true, reasons: [{ code: "no_agents", count: 1 }, { code: "no_balance", count: 1 }] }, null).label).toBe("Sin saldo");
    expect(stateView(es, "active", { needs: true, reasons: [{ code: "no_agents", count: 1 }] }, null).tone).toBe("positive");
    expect(reasonText(es, "no_agents", 1, null)).toBe("Sin agentes");
  });

  it("los agentes en texto, con plurales", () => {
    const s = (over: object) => ({ total: 0, serving: 0, testing: 0, ready_no_channel: 0, draft: 0, paused: 0, ...over });
    expect(agentsText(es, s({}), [])).toBe("Ninguno");
    expect(agentsText(es, s({ total: 1, serving: 1 }), [])).toBe("1 agente");
    expect(agentsText(es, s({ total: 5, testing: 2, paused: 2, draft: 1 }), [])).toBe("5 agentes · 2 en prueba · 2 pausados · 1 borrador");
    expect(agentsText(es, s({ total: 3, draft: 2, ready_no_channel: 1 }), [])).toBe("3 agentes · 2 borradores");
    // Sin el resumen, se cuentan los puntos (sin los archivados).
    expect(agentsText(es, null, [{ agent_id: "a", name: "A", visible_state: serving }, { agent_id: "b", name: "B", visible_state: { code: "archived", tone: "muted", pause_reason: null } }])).toBe("1 agente");
  });

  it("la minibarra mide lo gastado: ámbar desde el 80 %, roja sin saldo", () => {
    expect(bagBar(bag({ pct_spent: 25 }))).toEqual({ pct: 25, tone: "ok" });
    expect(bagBar(bag({ pct_spent: 80 }))).toEqual({ pct: 80, tone: "warn" });
    expect(bagBar(bag({ pct_spent: 130, state: "empty" }))).toEqual({ pct: 100, tone: "danger" });
    expect(bagBar({ ...bag(), state: "unassigned", pct_spent: null })).toEqual({ pct: 100, tone: "danger" });
    expect(bagBar(null)).toEqual({ pct: 100, tone: "danger" });
    expect(bagBar({ ...bag(), state: "unlimited" })).toBeNull();
  });

  it("los filtros y el menú en su orden, sin «Nuevo agente»", () => {
    expect(filterHref("all", "")).toBe("/clients");
    expect(filterHref("archived", " óptica ")).toBe("/clients?filter=archived&q=%C3%B3ptica");
    expect(parseFilter("nope")).toBe("all");
    expect(menuActions(["delete", "edit", "restore", "new_agent"])).toEqual(["edit", "restore", "delete"]);
  });
});
