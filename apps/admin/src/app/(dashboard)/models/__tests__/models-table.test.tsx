import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DeploymentRow } from "@/lib/backend-models";

import { DRIFT, POLICY, SOL, WHISPER, row } from "./fixtures";

const h = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: vi.fn(),
  createDeploymentAction: vi.fn(),
  unavailableAction: vi.fn(),
  addPriceAction: vi.fn(),
  cancelRetirementAction: vi.fn(),
  restoreAction: vi.fn(),
  putWeightsAction: vi.fn(),
  putSalePolicyAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { DeploymentsTable } = await import("../deployments-table");

beforeEach(() => h.refresh.mockReset());

function table(rows: DeploymentRow[], policy = POLICY) {
  return render(<DeploymentsTable rows={rows} policy={policy} routerVisible={false} />);
}

function rowOf(name: string): HTMLElement {
  const found = screen.getAllByRole("row").find((r) => within(r).queryByText(name, { selector: "span" }));
  if (!found) throw new Error(`no row for ${name}`);
  return found;
}

async function openMenu(name: string): Promise<HTMLElement> {
  await userEvent.click(within(rowOf(name)).getByRole("button", { name: `Más acciones de ${name}` }));
  return screen.findByRole("menu");
}

/** Spec 059, historia 4: a table of Modelos that reads in one screen. */
describe("the table of Modelos (4.1, 4.2)", () => {
  it("has five columns: Modelo, Proveedor, Coste, Venta and Acciones", () => {
    table([row()]);
    expect(screen.getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Modelo",
      "Proveedor",
      "Coste por millón",
      "Venta por millón",
      "Acciones",
    ]);
  });

  it("keeps the name of the model in the same row as «Precio», its one action in sight", () => {
    table([row(), SOL]);
    for (const name of ["Terra", "Sol"]) {
      const r = rowOf(name);
      expect(within(r).getByRole("button", { name: `Precio de ${name}` }).textContent).toBe("Precio");
      expect(within(r).getAllByRole("button").map((b) => b.textContent)).toEqual(["Precio", ""]);
    }
  });

  it("puts the provider and the residency in one cell", () => {
    table([row()]);
    const cells = within(rowOf("Terra")).getAllByRole("cell");
    expect(cells[1]!.textContent).toContain("openai");
    expect(cells[1]!.textContent).toContain("EE. UU.");
  });

  it("has the rest in its menu, with the destructive ones last and apart", async () => {
    table([row()]);
    const menu = await openMenu("Terra");
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Pesos de venta", "Retirar", "No disponible"]);
    expect(items.slice(-2).every((i) => i.getAttribute("data-variant") === "destructive")).toBe(true);
    const order = Array.from(menu.querySelectorAll('[role="menuitem"], [role="separator"]')).map((el) =>
      el.getAttribute("role") === "separator" ? "—" : el.textContent,
    );
    expect(order).toEqual(["Pesos de venta", "—", "Retirar", "No disponible"]);
  });

  it("a model in use keeps «Pesos de venta» and nothing destructive", async () => {
    table([SOL]);
    const menu = await openMenu("Sol");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Pesos de venta"]);
    expect(within(menu).queryByRole("separator")).toBeNull();
  });

  it("has an empty state that does not point to the router", () => {
    table([]);
    expect(screen.getByText("Ningún modelo con este estado")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Nuevo despliegue|router/i);
  });
});

describe("the cost and the sale of each model (3.1, 3.8, 3.11)", () => {
  it("shows the cost and the sale per million, lane by lane, with the multiplier of each", () => {
    table([row()]);
    const [, , cost, sale] = within(rowOf("Terra")).getAllByRole("cell");
    for (const text of ["Entrada", "Caché", "Salida", "4,00", "0,40", "20,00"]) expect(cost!.textContent).toContain(text);
    for (const text of ["8,80", "0,88", "44,00", "2,2×"]) expect(sale!.textContent).toContain(text);
    expect(within(sale!).getByText("En el objetivo")).toBeTruthy();
  });

  it("marks a sale that lags behind the target", () => {
    table([DRIFT]);
    const sale = within(rowOf("Terra")).getAllByRole("cell")[3]!;
    expect(within(sale).getByText("Desfasado")).toBeTruthy();
    expect(sale.textContent).toContain("1,76×");
  });

  it("marks a lane under the floor as a danger", () => {
    table([
      row({
        sale: {
          ...DRIFT.sale,
          state: "below_floor",
          lanes: { ...DRIFT.sale.lanes, output: { cost: "40.000000", weight: "4.400000", sale: "44.000000", multiplier: "1.10" } },
        },
      }),
    ]);
    const sale = within(rowOf("Terra")).getAllByRole("cell")[3]!;
    expect(within(sale).getByText("Bajo el suelo")).toBeTruthy();
    expect(within(sale).getByText(/1,1×/).getAttribute("data-floor")).toBe("below");
  });

  it("a model without weights says so", () => {
    table([row({ sale: { state: "unweighted", lanes: null, proposed: { input: "0.88", cache_read: "0.088", output: "4.4" } } })]);
    expect(within(rowOf("Terra")).getByText("Sin pesos")).toBeTruthy();
  });

  it("a model priced by the minute has no lanes nor weights to edit", async () => {
    table([WHISPER]);
    const r = rowOf("Whisper");
    expect(within(r).getByText("Por minuto")).toBeTruthy();
    expect(r.textContent).toContain("0,006");
    expect(r.textContent).toContain("no tiene pesos por carril");
    const menu = await openMenu("Whisper");
    expect(within(menu).queryByRole("menuitem", { name: "Pesos de venta" })).toBeNull();
  });

  it("a model without cost says it has no proposal", () => {
    table([row({ current_price: null, sale: { state: "no_cost", lanes: null, proposed: null } })]);
    const r = rowOf("Terra");
    expect(r.textContent).toContain("Sin coste");
    expect(r.textContent).toContain("sin propuesta");
  });
});
