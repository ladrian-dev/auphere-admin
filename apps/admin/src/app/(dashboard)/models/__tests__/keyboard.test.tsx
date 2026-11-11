import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DeploymentRow } from "@/lib/backend-models";

import { POLICY, row } from "./fixtures";

const h = vi.hoisted(() => ({
  retire: vi.fn(),
  unavailable: vi.fn(),
  cancel: vi.fn(),
  restore: vi.fn(),
  policy: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("../actions", () => ({
  activateAction: vi.fn(),
  retireAction: (...a: unknown[]) => h.retire(...a),
  createDeploymentAction: vi.fn(),
  unavailableAction: (...a: unknown[]) => h.unavailable(...a),
  addPriceAction: vi.fn(),
  cancelRetirementAction: (...a: unknown[]) => h.cancel(...a),
  restoreAction: (...a: unknown[]) => h.restore(...a),
  putWeightsAction: vi.fn(),
  putSalePolicyAction: (...a: unknown[]) => h.policy(...a),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { DeploymentsTable } = await import("../deployments-table");
const { MultiplierDialog } = await import("../deployment-dialogs");

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

function table(rows: DeploymentRow[]) {
  return render(<DeploymentsTable rows={rows} policy={POLICY} routerVisible={false} />);
}

/** Base UI's focus trap passes through guards on both sides: wait for the focus to settle, then look. */
const settledInside = (dialog: HTMLElement) =>
  waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

/** Walks the open menu with ↓ until the focused item says `label`. */
async function arrowTo(user: ReturnType<typeof userEvent.setup>, label: string) {
  for (let i = 0; i < 8 && document.activeElement?.textContent !== label; i++) await user.keyboard("{ArrowDown}");
  expect(document.activeElement?.getAttribute("role")).toBe("menuitem");
  expect(document.activeElement?.textContent).toBe(label);
}

/**
 * Workspace UI gate (WCAG 2.1.1, 2.1.2, 2.4.3): every write of Modelos works
 * from the keyboard alone, and the focus always comes back to what opened it.
 */
describe("Modelos with the keyboard", () => {
  it("reaches «Precio» and then «⋯» of each row, in that order", async () => {
    const user = userEvent.setup();
    table([row()]);
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Precio de Terra" }));
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Más acciones de Terra" }));
  });

  it("opens «⋯» with Enter, walks its items with the arrows and closes it with Escape, back on «⋯»", async () => {
    const user = userEvent.setup();
    table([row()]);
    const more = screen.getByRole("button", { name: "Más acciones de Terra" });
    more.focus();
    await user.keyboard("{Enter}");
    const menu = await screen.findByRole("menu");
    await waitFor(() => expect(menu.contains(document.activeElement)).toBe(true));
    // The highlighted item is the focused element, so `focus-visible` paints its ring.
    await arrowTo(user, "Retirar");
    await arrowTo(user, "No disponible");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    await waitFor(() => expect(more).toHaveFocus());
  });

  it("a dialog chosen in «⋯» with the keyboard holds the focus, closes with Escape and gives it back to «⋯»", async () => {
    const user = userEvent.setup();
    table([row()]);
    const more = screen.getByRole("button", { name: "Más acciones de Terra" });
    more.focus();
    await user.keyboard("{ArrowDown}");
    await screen.findByRole("menu");
    await arrowTo(user, "Retirar");
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Retirar Terra" });
    await settledInside(dialog);
    for (let i = 0; i < 6; i++) {
      await user.tab();
      await settledInside(dialog);
    }
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(more).toHaveFocus());
  });

  it("«Precio» opens its dialog with Enter and Escape gives the focus back to it", async () => {
    const user = userEvent.setup();
    table([row()]);
    const price = screen.getByRole("button", { name: "Precio de Terra" });
    price.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Coste de Terra" });
    await settledInside(dialog);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(price).toHaveFocus());
  });

  it("«Cambiar» the target multiplier opens with Enter and Escape gives the focus back to it", async () => {
    const user = userEvent.setup();
    render(<MultiplierDialog policy={POLICY} />);
    const change = screen.getByRole("button", { name: "Cambiar el multiplicador objetivo" });
    change.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Multiplicador objetivo de venta" });
    await settledInside(dialog);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(change).toHaveFocus());
  });

  it("after a write that leaves its answer on screen, the focus stays in the dialog, on a way to close it", async () => {
    const user = userEvent.setup();
    h.retire.mockResolvedValue({ ok: true, data: { deployment: row({ status: "retiring" }), proposals: [] } });
    table([row()]);
    await user.click(screen.getByRole("button", { name: "Más acciones de Terra" }));
    await user.click(await screen.findByRole("menuitem", { name: "Retirar" }));
    const dialog = await screen.findByRole("dialog", { name: "Retirar Terra" });
    await user.type(dialog.querySelector('input[type="date"]') as HTMLInputElement, "2026-12-01");
    await user.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Lo retira el proveedor");
    await user.click(within(dialog).getByRole("button", { name: "Registrar la retirada" }));
    await within(dialog).findByRole("status");
    await waitFor(() => expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cerrar" })));
  });
});

/** WCAG 3.3.1 and 4.1.2: a field the operator left wrong says so itself, not only in a note under the form. */
describe("the checks of the row dialogs", () => {
  it("«Retirar» without day nor reason marks both fields, each with its message", async () => {
    const user = userEvent.setup();
    table([row()]);
    await user.click(screen.getByRole("button", { name: "Más acciones de Terra" }));
    await user.click(await screen.findByRole("menuitem", { name: "Retirar" }));
    const dialog = await screen.findByRole("dialog", { name: "Retirar Terra" });
    await user.click(within(dialog).getByRole("button", { name: "Registrar la retirada" }));
    expect(h.retire).not.toHaveBeenCalled();

    const day = within(dialog).getByLabelText(/Se retira el/);
    expect(day).toHaveAttribute("aria-invalid", "true");
    expect(day).toHaveAccessibleDescription(/Elige el día de la retirada/);
    const reason = within(dialog).getByRole("textbox", { name: /Motivo/ });
    expect(reason).toHaveAttribute("aria-invalid", "true");
    expect(reason).toHaveAccessibleDescription(/Hace falta el motivo/);
  });

  it.each([
    ["No disponible", "Marcar Terra como no disponible", "Marcar no disponible", row()],
    ["Cancelar retirada", "Cancelar la retirada de Terra", "Cancelar la retirada", row({ status: "retiring", retire_after: "2026-12-01T00:00:00+00:00" })],
    ["Volver a disponible", "Volver a disponible: Terra", "Volver a disponible", row({ status: "unavailable" })],
  ])("«%s» without a reason marks its Motivo, and says it once", async (item, title, confirm, r) => {
    const user = userEvent.setup();
    table([r]);
    await user.click(screen.getByRole("button", { name: "Más acciones de Terra" }));
    await user.click(await screen.findByRole("menuitem", { name: item }));
    const dialog = await screen.findByRole("dialog", { name: title });
    await user.click(within(dialog).getByRole("button", { name: confirm }));
    const reason = within(dialog).getByRole("textbox", { name: /Motivo/ });
    expect(reason).toHaveAttribute("aria-invalid", "true");
    expect(reason).toHaveAccessibleDescription(/Hace falta el motivo/);
    expect(within(dialog).getAllByRole("alert")).toHaveLength(1);
  });
});
