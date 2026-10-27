import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";

import { USD, bag, noChannel, row } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
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
const { filterHref, menuActions, parseFilter, reasonText, stateView } = await import("../client-v2-model");
const { t } = await import("@/i18n/messages");

/**
 * Spec 047 (T065, historia 15): la lista dice quién necesita algo y por qué.
 * Cubre las columnas, el motivo (con su cuenta y sus días), los puntos de los
 * agentes, la bolsa, los filtros con contadores, la búsqueda vacía, los
 * nombres largos y el menú según el permiso; y pasa axe.
 */
const es = (key: Parameters<typeof t>[1], vars?: Record<string, string | number>) => t("es", key, vars);
const COUNTS = { all: 3, attention: 2, active: 3, archived: 0 };

function list(items = [row()], props: Partial<React.ComponentProps<typeof ClientsListV2>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <ClientsListV2 items={items} counts={COUNTS} filter="all" q="" total={items.length} page={1} limit={50} {...props} />
    </LocaleProvider>,
  );
}

describe("ClientsListV2", () => {
  it("pinta cada columna: nombre y nicho, estado, agentes, bolsa y menú", async () => {
    const { container } = list([
      row({
        external_client_ref: "floristeria-lirio",
        name: "Floristería Lirio",
        niche: "Floristería",
        attention: { needs: true, reasons: [{ code: "no_balance", count: 1 }] },
        bag: bag({ state: "empty", balance: USD(0), alerts: ["empty"] }),
      }),
      row({
        external_client_ref: "clinica-sonrisa",
        name: "Clínica Sonrisa",
        attention: { needs: true, reasons: [{ code: "low_balance", count: 1 }] },
        bag: bag({ balance: USD(8), assigned: USD(50), pct_left: 16, days_left: 4, state: "low" }),
      }),
      row({
        external_client_ref: "cafe-origen",
        name: "Café Origen",
        agents: [{ agent_id: "p", name: "Pedidos", visible_state: noChannel }],
        attention: { needs: true, reasons: [{ code: "agent_without_channel", count: 1 }] },
        bag: bag({ days_left: null, days_estimable: false }),
      }),
    ]);
    const table = screen.getByRole("region", { name: "Clientes del partner" });
    const rows = within(table).getAllByRole("row").slice(1);
    // El orden es el de la API: no se reordena aquí.
    expect(rows.map((r) => within(r).getAllByRole("link")[0]?.textContent)).toEqual(["Floristería Lirio", "Clínica Sonrisa", "Café Origen"]);
    expect(within(rows[0]!).getAllByText("Sin saldo").length).toBeGreaterThan(0);
    expect(within(rows[0]!).getByText("Floristería")).toBeTruthy();
    expect(within(rows[1]!).getByText("Saldo bajo · quedan 4 días")).toBeTruthy();
    expect(within(rows[1]!).getByText(/8,00\sUSD/)).toBeTruthy();
    expect(within(rows[1]!).getByText(/16 % libre/)).toBeTruthy();
    expect(within(rows[2]!).getByText("1 agente sin canal")).toBeTruthy();
    expect(within(rows[2]!).getByRole("img", { name: "Pedidos: Listo · sin canal" })).toBeTruthy();
    expect(within(rows[2]!).getByText(/Aún sin ritmo/)).toBeTruthy();
    // La tabla se desplaza dentro de su caja, nunca la página.
    expect(table.className).toContain("overflow-x-auto");
    expect(table.querySelector("table")?.className).toContain("min-w-[760px]");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("los filtros llevan sus contadores y la búsqueda vacía lo dice", async () => {
    const { container } = list([], { q: "dental", counts: { all: 0, attention: 0, active: 0, archived: 0 } });
    const filters = screen.getByRole("navigation", { name: "Filtrar clientes" });
    expect(within(filters).getByRole("link", { name: "Todos · 0" }).getAttribute("aria-current")).toBe("page");
    expect(within(filters).getByRole("link", { name: "Necesitan atención · 0" }).getAttribute("href")).toBe("/clients?filter=attention&q=dental");
    expect(screen.getByRole("status").textContent).toBe("Ningún cliente coincide con «dental».");
    expect(await axeViolations(container)).toEqual([]);
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

  it("el menú ⋯ ofrece solo lo permitido, con «Pedir saldo» para quien no asigna", async () => {
    const user = userEvent.setup();
    list([row({ allowed: ["edit", "request_balance", "new_agent", "archive"] })]);
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar" });
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Editar", "Pedir saldo", "Nuevo agente", "Archivar"]);
    expect(items).not.toContain("Eliminar");
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
    expect(stateView(es, "active", { needs: false, reasons: [] }, null).label).toBe("Todo en orden");
    expect(reasonText(es, "no_agents", 1, null)).toBe("Sin agentes");
  });

  it("los filtros y el menú en su orden", () => {
    expect(filterHref("all", "")).toBe("/clients");
    expect(filterHref("archived", " óptica ")).toBe("/clients?filter=archived&q=%C3%B3ptica");
    expect(parseFilter("nope")).toBe("all");
    expect(menuActions(["delete", "edit", "restore"])).toEqual(["edit", "restore", "delete"]);
  });
});
