import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DeploymentRow, SalePolicy } from "@/lib/backend-models";

import { DRIFT, POLICY, row } from "./fixtures";

const h = vi.hoisted(() => ({ weights: vi.fn(), success: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: vi.fn(),
  createDeploymentAction: vi.fn(),
  unavailableAction: vi.fn(),
  addPriceAction: vi.fn(),
  cancelRetirementAction: vi.fn(),
  restoreAction: vi.fn(),
  putWeightsAction: (...a: unknown[]) => h.weights(...a),
  putSalePolicyAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { DeploymentsTable } = await import("../deployments-table");

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

async function openWeights(r: DeploymentRow = DRIFT, policy: SalePolicy = POLICY) {
  render(<DeploymentsTable rows={[r]} policy={policy} routerVisible={false} />);
  await userEvent.click(screen.getByRole("button", { name: `Más acciones de ${r.display_name}` }));
  await userEvent.click(await screen.findByRole("menuitem", { name: "Pesos de venta" }));
  return screen.findByRole("dialog");
}

const weight = (dialog: HTMLElement, lane: string) =>
  within(dialog).getByRole("textbox", { name: new RegExp(`^${lane}`) }) as HTMLInputElement;

async function retype(input: HTMLInputElement, value: string) {
  await userEvent.clear(input);
  await userEvent.type(input, value);
}

/** Spec 059, historia 3: Auphere decides what each model sells for. */
describe("the weights dialog", () => {
  it("comes with the proposal of the target multiplier over the cost in force (3.3)", async () => {
    const dialog = await openWeights();
    expect(within(dialog).getByRole("heading", { name: "Pesos de venta de Terra" })).toBeTruthy();
    expect(weight(dialog, "Entrada").value).toBe("0,88");
    expect(weight(dialog, "Caché").value).toBe("0,088");
    expect(weight(dialog, "Salida").value).toBe("5,5");
    expect(dialog.textContent).toContain("2,2×");
    expect(dialog.textContent).toMatch(/no avisa a los partners/);
  });

  it("refuses a lane under the floor, naming it (3.4)", async () => {
    const dialog = await openWeights();
    await retype(weight(dialog, "Salida"), "3");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Prueba");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar los pesos" }));
    expect(h.weights).not.toHaveBeenCalled();
    const alert = within(dialog)
      .getAllByRole("alert")
      .find((a) => /suelo/.test(a.textContent ?? ""));
    expect(alert?.textContent).toMatch(/1,2×/);
    expect(weight(dialog, "Salida").getAttribute("aria-invalid")).toBe("true");
  });

  it("needs its reason (3.2)", async () => {
    const dialog = await openWeights();
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar los pesos" }));
    expect(h.weights).not.toHaveBeenCalled();
    expect(dialog.textContent).toContain("Hace falta el motivo");
  });

  it("saves the three weights with the reason, in force when saved", async () => {
    h.weights.mockResolvedValue({ ok: true, data: row() });
    const dialog = await openWeights();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Subió la salida");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar los pesos" }));
    expect(h.weights).toHaveBeenCalledWith("d1", { input: "0.88", cache_read: "0.088", output: "5.5", reason: "Subió la salida" });
    expect(h.refresh).toHaveBeenCalled();
  });

  it("says the refusal of the API in words", async () => {
    h.weights.mockResolvedValue({ ok: false, code: "below_floor", error: "La venta queda por debajo de 1,5 veces el coste en salida." });
    const dialog = await openWeights();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "x");
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar los pesos" }));
    expect(dialog.textContent).toContain("por debajo de 1,5 veces el coste en salida");
  });

  it("without the target multiplier, starts from the current weights and says it cannot propose (4.7)", async () => {
    const dialog = await openWeights(DRIFT, { ...POLICY, multiplier: null });
    expect(weight(dialog, "Salida").value).toBe("4,4");
    expect(dialog.textContent).toMatch(/no se pueden proponer pesos/);
  });

  it("without a cost in force, lets them be written by hand", async () => {
    const dialog = await openWeights(row({ current_price: null, sale: { state: "no_cost", lanes: null, proposed: null } }));
    expect(weight(dialog, "Salida").value).toBe("4,4");
    expect(dialog.textContent).toMatch(/Sin coste vigente/);
  });
});
