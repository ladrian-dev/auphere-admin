import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DRIFT, POLICY, SOL, row } from "./fixtures";

vi.mock("@/lib/router-panel", () => ({ ROUTER_PANEL_VISIBLE: false }));

const api = vi.hoisted(() => ({ listDeployments: vi.fn() }));
vi.mock("@/lib/backend-models", () => ({ modelsBackend: api }));
const h = vi.hoisted(() => ({ policy: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: vi.fn(),
  createDeploymentAction: vi.fn(),
  unavailableAction: vi.fn(),
  addPriceAction: vi.fn(),
  cancelRetirementAction: vi.fn(),
  restoreAction: vi.fn(),
  putWeightsAction: vi.fn(),
  putSalePolicyAction: (...a: unknown[]) => h.policy(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { default: ModelsPage } = await import("../page");
const { default: ModelsLoading } = await import("../loading");

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
  api.listDeployments.mockReset().mockResolvedValue({ items: [row(), SOL, DRIFT], statuses: [], sale_policy: POLICY });
});

async function page() {
  render(await ModelsPage({ searchParams: Promise.resolve({}) }));
}

const header = () => screen.getByRole("banner");

/** Spec 059, historias 3 y 4: the header of Modelos and its states. */
describe("the header of Modelos", () => {
  it("shows the target multiplier with «Cambiar»", async () => {
    await page();
    const target = within(header()).getByRole("group", { name: "Multiplicador objetivo" });
    expect(target.textContent).toContain("2,2×");
    expect(target.textContent).toContain("1,5×");
    expect(within(target).getByRole("button", { name: /Cambiar/ })).toBeTruthy();
  });

  it("promises no protection the system does not apply (4.6)", async () => {
    await page();
    const text = header().textContent ?? "";
    expect(text).not.toMatch(/Ninguno se usa/);
    expect(text).not.toMatch(/sin retención/);
    expect(text).not.toMatch(/certific/i);
    expect(text).not.toMatch(/router/i);
  });

  it("changes the multiplier with a reason, and offers to apply it to every model (3.6)", async () => {
    h.policy.mockResolvedValue({ ok: true, data: { sale_policy: { ...POLICY, multiplier: "2.5" }, applied_to: ["a", "b", "c"] } });
    await page();
    await userEvent.click(within(header()).getByRole("button", { name: /Cambiar/ }));
    const dialog = await screen.findByRole("dialog");
    const value = within(dialog).getByRole("textbox", { name: /^Multiplicador/ }) as HTMLInputElement;
    expect(value.value).toBe("2,2");
    expect(dialog.textContent).toMatch(/1,5×/);
    expect(dialog.textContent).toMatch(/no avisa a los partners/);
    await userEvent.clear(value);
    await userEvent.type(value, "2,5");
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "Aplicar a todos los modelos" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el multiplicador" }));
    expect(h.policy).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Margen del trimestre");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el multiplicador" }));
    expect(h.policy).toHaveBeenCalledWith({ multiplier: "2.5", apply_to_all: true, reason: "Margen del trimestre" });
    expect(within(dialog).getByRole("status").textContent).toContain("3 modelos");
  });

  it("refuses a multiplier under the floor (3.7)", async () => {
    await page();
    await userEvent.click(within(header()).getByRole("button", { name: /Cambiar/ }));
    const dialog = await screen.findByRole("dialog");
    const value = within(dialog).getByRole("textbox", { name: /^Multiplicador/ });
    await userEvent.clear(value);
    await userEvent.type(value, "1,2");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "x");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar el multiplicador" }));
    expect(h.policy).not.toHaveBeenCalled();
    expect(dialog.textContent).toMatch(/1,5/);
  });
});

describe("the states of Modelos (4.7)", () => {
  it("loading: the table it will be, with its own columns, not a generic grid", () => {
    render(<ModelsLoading />);
    const loading = screen.getByRole("status", { name: "Cargando los modelos" });
    expect(within(loading).getAllByRole("columnheader", { hidden: true }).map((c) => c.textContent)).toEqual([
      "Modelo",
      "Proveedor",
      "Coste por millón",
      "Venta por millón",
      "Acciones",
    ]);
  });

  it("ideal: every model, in its table", async () => {
    await page();
    expect(screen.getAllByRole("row")).toHaveLength(4);
  });

  it("partial: without the target multiplier, the models are there and it says it cannot propose weights", async () => {
    api.listDeployments.mockResolvedValue({ items: [row(), SOL], statuses: [], sale_policy: { ...POLICY, multiplier: null } });
    await page();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(document.body.textContent).toMatch(/no se pueden proponer pesos/);
    expect(within(header()).getByRole("group", { name: "Multiplicador objetivo" }).textContent).toContain("Sin leer");
  });

  it("error: says the catalog could not be read", async () => {
    api.listDeployments.mockRejectedValue(new Error("down"));
    await page();
    expect(screen.getByText("No se pudo leer el catálogo")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Multiplicador objetivo" })).toBeNull();
  });

  it("error: offers «Reintentar», which reads the catalog again", async () => {
    api.listDeployments.mockRejectedValue(new Error("down"));
    await page();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(h.refresh).toHaveBeenCalledTimes(1);
  });

  it("empty: says there is no model with this state", async () => {
    api.listDeployments.mockResolvedValue({ items: [], statuses: [], sale_policy: POLICY });
    await page();
    expect(screen.getByText("Ningún modelo con este estado")).toBeTruthy();
  });

  it("when the worker's models cannot be checked, says what that means for «Retirar» and «No disponible»", async () => {
    const unverified = { ...row().uses, verified: false, problem: "no_heartbeat" as const };
    api.listDeployments.mockResolvedValue({ items: [row({ uses: unverified })], statuses: [], sale_policy: POLICY });
    await page();
    expect(document.body.textContent).toMatch(/No se puede comprobar qué modelos usa la plataforma/);
    expect(document.body.textContent).toMatch(/ningún worker/);
  });
});
