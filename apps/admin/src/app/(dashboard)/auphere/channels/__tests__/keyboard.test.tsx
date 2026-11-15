import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuphereOwnerChannelOut } from "@/lib/backend";

const h = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn(), deactivate: vi.fn(), refresh: vi.fn() }));
vi.mock("../actions", () => ({
  createNumberAction: (...a: unknown[]) => h.create(...a),
  updateNumberAction: (...a: unknown[]) => h.update(...a),
  deactivateNumberAction: (...a: unknown[]) => h.deactivate(...a),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: h.refresh }) }));

const { NumbersTable } = await import("../numbers-table");
const { CreateNumberDialog } = await import("../number-dialogs");

const CL: AuphereOwnerChannelOut = {
  id: "c1",
  phone_e164: "+56912345678",
  display_name: "Auphere CL",
  country_code: "CL",
  provider: "meta",
  provider_phone_id: "1029384756",
  active: true,
  is_default: true,
  has_webhook_secret: true,
  has_access_token: true,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
};

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset();
});

const settledInside = (dialog: HTMLElement) =>
  waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));

/**
 * Workspace UI gate (WCAG 2.1.1, 2.1.2, 2.4.3): Números de Auphere from the
 * keyboard alone, with the focus back on what opened each dialog.
 */
describe("Números de Auphere with the keyboard", () => {
  it("reaches «Editar» and then «⋯» of each row, in that order", async () => {
    const user = userEvent.setup();
    render(<NumbersTable numbers={[CL]} />);
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Editar Auphere CL" }));
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Más acciones de Auphere CL" }));
  });

  it("opens «⋯» with Enter, walks it with the arrows and closes it with Escape, back on «⋯»", async () => {
    const user = userEvent.setup();
    render(<NumbersTable numbers={[CL]} />);
    const more = screen.getByRole("button", { name: "Más acciones de Auphere CL" });
    more.focus();
    await user.keyboard("{Enter}");
    const menu = await screen.findByRole("menu");
    await waitFor(() => expect(menu.contains(document.activeElement)).toBe(true));
    for (let i = 0; i < 4 && document.activeElement?.textContent !== "Desactivar"; i++) await user.keyboard("{ArrowDown}");
    expect(document.activeElement?.getAttribute("role")).toBe("menuitem");
    expect(document.activeElement?.textContent).toBe("Desactivar");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    await waitFor(() => expect(more).toHaveFocus());
  });

  it("«Desactivar» chosen with the keyboard holds the focus in its dialog and Escape gives it back to «⋯»", async () => {
    const user = userEvent.setup();
    render(<NumbersTable numbers={[CL]} />);
    const more = screen.getByRole("button", { name: "Más acciones de Auphere CL" });
    more.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("menu");
    for (let i = 0; i < 4 && document.activeElement?.textContent !== "Desactivar"; i++) await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Desactivar Auphere CL" });
    await settledInside(dialog);
    for (let i = 0; i < 5; i++) {
      await user.tab();
      await settledInside(dialog);
    }
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(more).toHaveFocus());
  });

  it("«Editar» opens with Enter and Escape gives the focus back to it", async () => {
    const user = userEvent.setup();
    render(<NumbersTable numbers={[CL]} />);
    const edit = screen.getByRole("button", { name: "Editar Auphere CL" });
    edit.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Editar Auphere CL" });
    await settledInside(dialog);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(edit).toHaveFocus());
  });

  it("«Registrar un número» opens with Enter and Escape gives the focus back to it", async () => {
    const user = userEvent.setup();
    render(<CreateNumberDialog />);
    const register = screen.getByRole("button", { name: "Registrar un número" });
    register.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Registrar un número de Auphere" });
    await settledInside(dialog);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(register).toHaveFocus());
  });
});

/** WCAG 2.5.3 and the long-text gate: a label is the field's name; what to do with it goes in its hint. */
describe("the fields of «Editar»", () => {
  it("names the token by its label and says in its hint that an empty one keeps the saved token", async () => {
    const user = userEvent.setup();
    render(<NumbersTable numbers={[CL]} />);
    await user.click(screen.getByRole("button", { name: "Editar Auphere CL" }));
    const dialog = await screen.findByRole("dialog");
    const token = within(dialog).getByLabelText(/Token de acceso de Meta/);
    expect(token).toHaveAccessibleName(/^Token de acceso de Meta\s*Opcional$/);
    expect(token).toHaveAccessibleDescription(/Déjalo vacío para conservar el actual/);
  });

  it("without a saved token, says it is missing", async () => {
    const user = userEvent.setup();
    render(<NumbersTable numbers={[{ ...CL, has_access_token: false }]} />);
    await user.click(screen.getByRole("button", { name: "Editar Auphere CL" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Token de acceso de Meta/)).toHaveAccessibleName(/^Token de acceso de Meta\s*Falta$/);
  });
});
