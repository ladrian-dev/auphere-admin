import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DeploymentRow } from "@/lib/backend-models";

import { POLICY, SOL, row } from "./fixtures";

const h = vi.hoisted(() => ({
  activate: vi.fn(),
  retire: vi.fn(),
  create: vi.fn(),
  unavailable: vi.fn(),
  price: vi.fn(),
  cancel: vi.fn(),
  restore: vi.fn(),
  weights: vi.fn(),
  policy: vi.fn(),
  success: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("../actions", () => ({
  activateAction: (...a: unknown[]) => h.activate(...a),
  retireAction: (...a: unknown[]) => h.retire(...a),
  createDeploymentAction: (...a: unknown[]) => h.create(...a),
  unavailableAction: (...a: unknown[]) => h.unavailable(...a),
  addPriceAction: (...a: unknown[]) => h.price(...a),
  cancelRetirementAction: (...a: unknown[]) => h.cancel(...a),
  restoreAction: (...a: unknown[]) => h.restore(...a),
  putWeightsAction: (...a: unknown[]) => h.weights(...a),
  putSalePolicyAction: (...a: unknown[]) => h.policy(...a),
}));
vi.mock("sonner", () => ({ toast: { success: h.success, error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { DeploymentsTable } = await import("../deployments-table");

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

function table(rows: DeploymentRow[]) {
  return render(<DeploymentsTable rows={rows} policy={POLICY} routerVisible={false} />);
}

function rowOf(name: string): HTMLElement {
  const found = screen.getAllByRole("row").find((r) => within(r).queryByText(name, { selector: "span" }));
  if (!found) throw new Error(`no row for ${name}`);
  return found;
}

/** Opens the «⋯» menu of a row and returns the names of its items, in order; none without a menu. */
async function menuOf(name: string): Promise<string[]> {
  const trigger = within(rowOf(name)).queryByRole("button", { name: `Más acciones de ${name}` });
  if (!trigger) return [];
  await userEvent.click(trigger);
  const items = await screen.findAllByRole("menuitem");
  return items.map((i) => i.textContent ?? "");
}

async function pick(name: string, item: string) {
  await userEvent.click(within(rowOf(name)).getByRole("button", { name: `Más acciones de ${name}` }));
  await userEvent.click(await screen.findByRole("menuitem", { name: item }));
  return screen.findByRole("dialog");
}

/** Spec 059, historia 1: nobody silences the agents from the panel. */
describe("a model in use (1.1, 1.2)", () => {
  it("does not offer «Retirar» nor «No disponible», and says what uses it, in words", async () => {
    table([SOL]);
    const sol = rowOf("Sol");
    expect(within(sol).getByText("En uso")).toBeTruthy();
    expect(sol.textContent).toContain("responder");
    expect(sol.textContent).toContain("reserva de responder");
    expect(sol.textContent).toContain("7 agentes de Amigable Cobro y New Air Climatización");
    const items = await menuOf("Sol");
    expect(items).not.toContain("Retirar");
    expect(items).not.toContain("No disponible");
  });

  it("a model only assigned by a client is in use too", async () => {
    table([row({ uses: { defaults: [], agents: 0, clients: ["Spa Jemma"], verified: true, problem: null } })]);
    expect(within(rowOf("Terra")).getByText("En uso")).toBeTruthy();
    expect(rowOf("Terra").textContent).toContain("Spa Jemma");
    const items = await menuOf("Terra");
    expect(items).not.toContain("Retirar");
    expect(items).not.toContain("No disponible");
  });

  it("a model nobody uses offers both, at the end of its menu (1.3)", async () => {
    table([row()]);
    expect(within(rowOf("Terra")).queryByText("En uso")).toBeNull();
    const items = await menuOf("Terra");
    expect(items.slice(-2)).toEqual(["Retirar", "No disponible"]);
  });

  it("an unknown use of the registry is still named", () => {
    table([row({ uses: { defaults: ["new_task_2027"], agents: 0, clients: [], verified: true, problem: null } })]);
    expect(rowOf("Terra").textContent).toContain("new_task_2027");
  });
});

describe("the way back (1.6, 1.7)", () => {
  it("a model in retirement offers «Cancelar retirada», with its reason", async () => {
    h.cancel.mockResolvedValue({ ok: true, data: row() });
    table([row({ status: "retiring", retire_after: "2026-12-01T00:00:00+00:00" })]);
    const items = await menuOf("Terra");
    expect(items).toContain("Cancelar retirada");
    expect(items).not.toContain("Retirar");
    await userEvent.keyboard("{Escape}");
    const dialog = await pick("Terra", "Cancelar retirada");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar la retirada" }));
    expect(h.cancel).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("alert").textContent).toContain("Hace falta el motivo");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Nos equivocamos de modelo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar la retirada" }));
    expect(h.cancel).toHaveBeenCalledWith("d1", "Nos equivocamos de modelo");
    expect(h.refresh).toHaveBeenCalled();
  });

  it("a model «No disponible» offers «Volver a disponible», with its reason", async () => {
    h.restore.mockResolvedValue({ ok: true, data: row() });
    table([row({ status: "unavailable" })]);
    const items = await menuOf("Terra");
    expect(items).toContain("Volver a disponible");
    expect(items).not.toContain("No disponible");
    await userEvent.keyboard("{Escape}");
    const dialog = await pick("Terra", "Volver a disponible");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "El DPA ya está firmado");
    await userEvent.click(within(dialog).getByRole("button", { name: "Volver a disponible" }));
    expect(h.restore).toHaveBeenCalledWith("d1", "El DPA ya está firmado");
  });

  it("closing a dialog opened from the menu gives the focus back to the menu", async () => {
    table([row({ status: "unavailable" })]);
    await pick("Terra", "Volver a disponible");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Más acciones de Terra" })),
    );
  });

  it("an active model offers neither", async () => {
    table([row()]);
    const items = await menuOf("Terra");
    expect(items).not.toContain("Cancelar retirada");
    expect(items).not.toContain("Volver a disponible");
  });
});

describe("a stopped retirement (1.8)", () => {
  it("is painted with the number of agents, even on a model in use", () => {
    table([
      row({ status: "retiring", retirement_blocked_agents: 3, uses: { ...SOL.uses } }),
      row({ uuid: "d2", display_name: "Luna", status: "retiring", retirement_blocked_agents: 1 }),
      row({ uuid: "d3", display_name: "Nube", status: "retiring", retirement_blocked_agents: 0 }),
    ]);
    expect(within(rowOf("Terra")).getByText("Retirada detenida (3 agentes)")).toBeTruthy();
    expect(within(rowOf("Luna")).getByText("Retirada detenida (1 agente)")).toBeTruthy();
    expect(within(rowOf("Nube")).queryByText(/Retirada detenida/)).toBeNull();
  });
});

describe("the dialogs say what the action does, without a router (1.9)", () => {
  it.each([
    ["Retirar", row()],
    ["No disponible", row()],
    ["Cancelar retirada", row({ status: "retiring", retire_after: "2026-12-01T00:00:00+00:00" })],
    ["Volver a disponible", row({ status: "unavailable" })],
  ])("«%s»", async (item, r) => {
    table([r]);
    const dialog = await pick("Terra", item);
    expect(dialog.textContent).not.toMatch(/router/i);
    expect(dialog.textContent).not.toMatch(/Automático/);
  });

  it("«Precio»", async () => {
    table([row()]);
    await userEvent.click(within(rowOf("Terra")).getByRole("button", { name: "Precio de Terra" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).not.toMatch(/router/i);
  });
});

describe("a refusal of the API is said in words (1.4)", () => {
  it("«No disponible» refused because the model is in use", async () => {
    h.unavailable.mockResolvedValue({
      ok: false,
      code: "model_in_use",
      error: "Terra está en uso: por defecto para responder. No cambia de estado.",
    });
    table([row()]);
    const dialog = await pick("Terra", "No disponible");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Lo retira el proveedor");
    await userEvent.click(within(dialog).getByRole("button", { name: "Marcar no disponible" }));
    expect(h.unavailable).toHaveBeenCalledWith("d1", "Lo retira el proveedor");
    expect(within(dialog).getByRole("alert").textContent).toContain("por defecto para responder");
    expect(h.refresh).not.toHaveBeenCalled();
  });

  it("«Retirar» with its day and its reason", async () => {
    h.retire.mockResolvedValue({ ok: true, data: { deployment: row({ status: "retiring" }), proposals: [] } });
    const { rerender } = table([row()]);
    const dialog = await pick("Terra", "Retirar");
    const date = dialog.querySelector('input[type="date"]') as HTMLInputElement;
    await userEvent.type(date, "2026-12-01");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Lo retira el proveedor");
    await userEvent.click(within(dialog).getByRole("button", { name: "Registrar la retirada" }));
    expect(h.retire).toHaveBeenCalledWith("d1", {
      retire_after: "2026-12-01T00:00:00+00:00",
      reason: "Lo retira el proveedor",
    });
    expect(within(dialog).getByRole("status").textContent).toContain("Ningún agente responde con este modelo");
    // After the refresh the row is in retirement and no longer offers «Retirar»:
    // the confirmation stays on screen until it is closed.
    rerender(
      <DeploymentsTable rows={[row({ status: "retiring", retire_after: "2026-12-01T00:00:00+00:00" })]} policy={POLICY} routerVisible={false} />,
    );
    expect(screen.getByRole("dialog").textContent).toContain("Ningún agente responde con este modelo");
  });
});
