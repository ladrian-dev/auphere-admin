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
const { agentsText, bagBar, bagPace, filterHref, menuActions, parseFilter, reasonText, stateView } = await import("../client-v2-model");
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

/** La tabla de escritorio (desde 760 px). */
function desktop() {
  return within(screen.getByRole("region", { name: "Clientes del partner" }));
}

function bodyRows() {
  return desktop().getAllByRole("row").slice(1);
}

/** Las tarjetas del móvil (por debajo de 760 px), spec 074 (M01). */
function cards() {
  const list = screen.getByRole("list", { name: "Clientes del partner" });
  return Array.from(list.querySelectorAll<HTMLElement>(":scope > [data-slot=client-card]"));
}

/** La línea de la minibarra: «{x} · quedan de {y}» o «Sin saldo asignado» (spec 072, 2.1). */
function line(r: HTMLElement) {
  return r.querySelector("[data-slot=bag-line]")?.textContent?.trim();
}

/** La línea de cuánto dura (spec 072, 2.2). */
function pace(r: HTMLElement) {
  return r.querySelector("[data-slot=bag-pace]")?.textContent?.trim();
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
    // Spec 072 (2.1): la barra es lo que queda; sin saldo, vacía.
    expect(fill(rows[0]!).fill?.style.width).toBe("0%");
    expect(pace(rows[0]!)).toBeUndefined();

    // Flor y Encanto: «Al día», los agentes en texto y lo que queda de lo asignado.
    expect(within(rows[1]!).getByText("Al día")).toBeTruthy();
    expect(within(rows[1]!).getByText("3 agentes · 1 en prueba · 1 pausado")).toBeTruthy();
    expect(line(rows[1]!)).toMatch(/^17,70\sUSD · quedan de 60,00\sUSD$/);
    expect(within(rows[1]!).getByRole("img", { name: "Ventas mayoristas: En prueba" })).toBeTruthy();
    expect(fill(rows[1]!).fill?.style.width).toBe("29.5%");
    expect(fill(rows[1]!).bar?.dataset.tone).toBe("ok");
    // Spec 072 (2.2, 2.6): cuánto dura, a la vista; la barra dice lo mismo que se lee.
    expect(pace(rows[1]!)).toBe("Unos 12 días a este ritmo");
    expect(fill(rows[1]!).bar).toHaveAttribute("role", "meter");
    expect(fill(rows[1]!).bar?.getAttribute("aria-label")?.replace(/\s/g, " ")).toBe("17,70 USD · quedan de 60,00 USD. Unos 12 días a este ritmo");

    // Clínica: saldo bajo por la regla de la API (`state: "low"`), en ámbar (spec 072, 2.3).
    expect(within(rows[2]!).getByText("Saldo bajo · quedan 4 días")).toBeTruthy();
    expect(fill(rows[2]!).bar?.dataset.tone).toBe("warn");
    expect(fill(rows[2]!).fill?.style.width).toBe("16%");
    expect(pace(rows[2]!)).toBe("Unos 4 días a este ritmo");

    // Pedidos: el saldo agotado. El Estado solo dice el estado: lo de los agentes
    // está en su columna (Andrés, 2026-10-28).
    const estado = rows[3]!.querySelectorAll("td")[1] as HTMLElement;
    expect(estado.textContent).not.toMatch(/agente/);
    expect(within(rows[3]!).getByRole("img", { name: "Pedidos: Listo · sin canal" })).toBeTruthy();
    expect(line(rows[3]!)).toMatch(/^0,00\sUSD · quedan de 200,00\sUSD$/);
    expect(fill(rows[3]!).bar?.dataset.tone).toBe("danger");
    expect(fill(rows[3]!).fill?.style.width).toBe("0%");

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
    expect(desktop().getByRole("status").textContent).toBe("Ningún cliente coincide con «dental».");
    expect(desktop().getByRole("status").closest("td")?.getAttribute("colspan")).toBe("5");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("un filtro vacío dice «Nada por aquí.»", () => {
    list([], { filter: "archived", counts: { all: 4, attention: 0, active: 4, archived: 0 } });
    expect(desktop().getByRole("status").textContent).toBe("Nada por aquí.");
  });

  it("sin clientes invita a crear el primero", () => {
    list([], { counts: { all: 0, attention: 0, active: 0, archived: 0 } });
    expect(screen.getByText("Todavía no hay clientes")).toBeTruthy();
  });

  it("aguanta un nombre y un nicho largos sin partir la fila", () => {
    const name = "Friseursalon Haarschneidekunst und Bartpflege Großstadt";
    list([row({ name, niche: "Herrenfriseur mit Rasurservice und Bartpflegeberatung" })]);
    const link = desktop().getByRole("link", { name });
    expect(link.className).toContain("truncate");
    expect(link.getAttribute("title")).toBe(name);
  });

  it("el menú ⋯ trae iconos y solo lo permitido, con «Pedir saldo» para quien no asigna", async () => {
    const user = userEvent.setup();
    list([row({ allowed: ["edit", "request_balance", "new_agent", "archive"] })]);
    await user.click(desktop().getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    const items = screen.getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Editar cliente", "Pedir saldo", "Archivar"]);
    for (const item of items) expect(item.querySelector("svg")).toBeTruthy();
    expect(screen.getAllByRole("separator")).toHaveLength(1);
  });

  it("con todo permitido: editar, asignar, separador, archivar y «Eliminar…»", async () => {
    const user = userEvent.setup();
    list([row()]);
    await user.click(desktop().getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Editar cliente", "Asignar saldo", "Archivar", "Eliminar…"]);
  });
});

describe("ClientsListV2 en el móvil (spec 074, M01)", () => {
  beforeEach(() => vi.clearAllMocks());

  const flor = () =>
    row({
      external_client_ref: "flor-y-encanto",
      name: "Flor y Encanto",
      niche: "Floristería",
      agents: [
        { agent_id: "r", name: "Recepción", visible_state: serving },
        { agent_id: "v", name: "Ventas mayoristas", visible_state: { code: "testing", tone: "info", pause_reason: null } },
      ],
      agents_summary: { total: 2, serving: 1, testing: 1, ready_no_channel: 0, draft: 0, paused: 0 },
      bag: bag({ balance: USD(17.7), assigned: USD(60), spent: USD(42.3), pct_spent: 70.5, pct_left: 29.5, days_left: 12 }),
    });
  const clinica = () =>
    row({
      external_client_ref: "clinica-sonrisa",
      name: "Clínica Sonrisa",
      niche: null,
      attention: { needs: true, reasons: [{ code: "low_balance", count: 1 }] },
      bag: bag({ balance: USD(8), assigned: USD(50), spent: USD(42), pct_spent: 84, pct_left: 16, days_left: 4, state: "low" }),
    });

  it("por debajo de 760 px, una tarjeta por cliente con todo lo de su fila; desde 760 px, la tabla", async () => {
    const { container } = list([flor(), clinica()]);
    const region = screen.getByRole("region", { name: "Clientes del partner" });
    const phone = screen.getByRole("list", { name: "Clientes del partner" });
    // El mismo punto de ruptura que la tabla (`min-w-[760px]`): o tabla o tarjetas.
    expect(region.className).toContain("max-[760px]:hidden");
    expect(phone.className).toContain("min-[760px]:hidden");
    expect(phone.className).not.toContain("max-[760px]");

    const [first, second] = cards();
    expect(cards()).toHaveLength(2);
    // El orden es el de la API, como en la tabla.
    expect(cards().map((c) => within(c).getByRole("link").textContent)).toEqual(["Flor y Encanto", "Clínica Sonrisa"]);

    // El nombre es el enlace (y el foco de teclado), con su nicho debajo.
    const link = within(first!).getByRole("link", { name: "Flor y Encanto" });
    expect(link.getAttribute("href")).toBe("/clients/flor-y-encanto");
    expect(link.className).toContain("truncate");
    expect(link.className).toContain("py-3");
    expect(within(first!).getByText("Floristería")).toBeTruthy();
    // El estado, los agentes en texto con sus puntos y el saldo con su barra.
    expect(within(first!).getByText("Al día")).toBeTruthy();
    expect(within(first!).getByText("2 agentes · 1 en prueba")).toBeTruthy();
    expect(within(first!).getByRole("img", { name: "Ventas mayoristas: En prueba" })).toBeTruthy();
    expect(line(first!)).toMatch(/^17,70\sUSD · quedan de 60,00\sUSD$/);
    expect(pace(first!)).toBe("Unos 12 días a este ritmo");
    const meter = within(first!).getByRole("meter");
    expect(meter.getAttribute("aria-label")?.replace(/\s/g, " ")).toBe("17,70 USD · quedan de 60,00 USD. Unos 12 días a este ritmo");
    expect(meter.dataset.tone).toBe("ok");
    expect(meter.className).toContain("w-full");
    // El ⋯ de siempre, con 44 × 44 de objetivo táctil.
    const more = within(first!).getByRole("button", { name: "Acciones de Flor y Encanto" });
    expect(more.className).toContain("size-11");

    // Saldo bajo: el ámbar va en la barra y en su línea, nunca en la tarjeta.
    expect(within(second!).getByText("Saldo bajo · quedan 4 días")).toBeTruthy();
    expect(fill(second!).bar?.dataset.tone).toBe("warn");
    expect(second!.querySelector("[data-slot=bag-pace]")?.className).toContain("text-status-warning-text");
    expect(second!.className).not.toMatch(/warning/);
    // Sin nicho, solo el nombre.
    expect(within(second!).getAllByRole("link")).toHaveLength(1);

    expect(await axeViolations(container)).toEqual([]);
  });

  it("la tabla de escritorio sigue igual: columnas, anchura y el ⋯ de 32 px", () => {
    list([flor()]);
    const table = desktop();
    expect(table.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Cliente", "Estado", "Agentes", "Saldo", "Acciones"]);
    expect(screen.getByRole("region", { name: "Clientes del partner" }).querySelector("table")?.className).toContain("min-w-[760px]");
    const more = table.getByRole("button", { name: "Acciones de Flor y Encanto" });
    expect(more.className).toContain("size-8");
    expect(more.className).not.toContain("size-11");
    const [r] = bodyRows();
    expect(line(r!)).toMatch(/^17,70\sUSD · quedan de 60,00\sUSD$/);
    expect(r!.querySelector("[data-slot=bag-line]")?.className).toContain("whitespace-nowrap");
    expect(fill(r!).bar?.className).toContain("w-30");
    expect(within(r!).getByText("2 agentes · 1 en prueba").className).toContain("whitespace-nowrap");
  });

  it("toda la tarjeta abre el cliente; el ⋯ no", async () => {
    const user = userEvent.setup();
    list([flor()]);
    const [card] = cards();
    await user.click(within(card!).getByText("Floristería"));
    expect(nav.push).toHaveBeenCalledWith("/clients/flor-y-encanto");
    nav.push.mockClear();
    await user.click(within(card!).getByText("2 agentes · 1 en prueba"));
    expect(nav.push).toHaveBeenCalledWith("/clients/flor-y-encanto");
    nav.push.mockClear();
    await user.click(within(card!).getByRole("button", { name: "Acciones de Flor y Encanto" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("el ⋯ del móvil trae las mismas acciones que el de escritorio, según el permiso", async () => {
    const user = userEvent.setup();
    list([flor()]);
    await user.click(within(cards()[0]!).getByRole("button", { name: "Acciones de Flor y Encanto" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Editar cliente", "Asignar saldo", "Archivar", "Eliminar…"]);
  });

  it("quien no asigna ve «Pedir saldo» en el ⋯ del móvil; sin acciones, no hay ⋯", async () => {
    const user = userEvent.setup();
    list([row({ allowed: ["edit", "request_balance", "new_agent", "archive"] }), row({ external_client_ref: "solo-ver", name: "Solo ver", allowed: ["new_agent"] })]);
    const [first, second] = cards();
    await user.click(within(first!).getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Editar cliente", "Pedir saldo", "Archivar"]);
    expect(within(second!).queryByRole("button")).toBeNull();
  });

  it("un saldo sin límite lo dice en la tarjeta, sin barra", () => {
    list([row({ bag: { ...bag(), state: "unlimited" } })]);
    const [card] = cards();
    expect(within(card!).getByText("Sin límite (lo cubre Auphere)")).toBeTruthy();
    expect(within(card!).queryByRole("meter")).toBeNull();
  });

  it("la búsqueda sin resultados lo dice también en el móvil", async () => {
    const { container } = list([], { q: "dental", counts: { all: 4, attention: 0, active: 4, archived: 0 } });
    const empty = container.querySelector<HTMLElement>("[data-slot=clients-cards-empty]");
    expect(empty?.className).toContain("min-[760px]:hidden");
    expect(within(empty!).getByRole("status").textContent).toBe("Ningún cliente coincide con «dental».");
    expect(screen.queryByRole("list", { name: "Clientes del partner" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
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

  it("la minibarra se llena con lo que queda; el ámbar sale de la regla, no de un umbral (spec 072, 2.1 y 2.3)", () => {
    expect(bagBar(bag({ pct_spent: 25, pct_left: 75 }))).toEqual({ pct: 75, tone: "ok" });
    // Gastado el 85 % pero la API no lo da por bajo (le quedan semanas): sin ámbar.
    expect(bagBar(bag({ pct_spent: 85, pct_left: 15 }))).toEqual({ pct: 15, tone: "ok" });
    expect(bagBar(bag({ pct_spent: 40, pct_left: 60, state: "low" }))).toEqual({ pct: 60, tone: "warn" });
    // Sin `pct_left`, lo que no se ha gastado.
    expect(bagBar(bag({ pct_spent: 30, pct_left: null }))).toEqual({ pct: 70, tone: "ok" });
    expect(bagBar(bag({ pct_spent: 130, state: "empty" }))).toEqual({ pct: 0, tone: "danger" });
    expect(bagBar({ ...bag(), state: "unassigned", pct_spent: null })).toEqual({ pct: 0, tone: "danger" });
    expect(bagBar(null)).toEqual({ pct: 0, tone: "danger" });
    expect(bagBar({ ...bag(), state: "unlimited" })).toBeNull();
  });

  it("cuánto dura, en una línea que dice qué falta si no se puede estimar (spec 072, 2.2)", () => {
    expect(bagPace(es, bag({ days_left: 78.6, days_estimable: true }))).toBe("Unos 79 días a este ritmo");
    expect(bagPace(es, bag({ days_left: 0.4, days_estimable: true }))).toBe("Menos de un día a este ritmo");
    expect(bagPace(es, bag({ days_left: null, days_estimable: false }))).toBe("Aún no hay gasto para calcular cuánto dura");
    expect(bagPace(es, bag({ state: "empty" }))).toBeNull();
    expect(bagPace(es, { ...bag(), state: "unassigned" })).toBeNull();
    expect(bagPace(es, null)).toBeNull();
  });

  it("los filtros y el menú en su orden, sin «Nuevo agente»", () => {
    expect(filterHref("all", "")).toBe("/clients");
    expect(filterHref("archived", " óptica ")).toBe("/clients?filter=archived&q=%C3%B3ptica");
    expect(parseFilter("nope")).toBe("all");
    expect(menuActions(["delete", "edit", "restore", "new_agent"])).toEqual(["edit", "restore", "delete"]);
  });
});
