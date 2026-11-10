import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(),
  nicheSuggestionsAction: vi.fn(),
}));

const { NewClientButton } = await import("../new-client-button");

/** Spec 047 (historia 3, escenario 6): crear lleva al Panel con «{nombre} creado.». */

const ok = <T,>(data: T) => ({ ok: true as const, data });
const actions = {
  detect: vi.fn(async () =>
    ok({ links: [], deduced: { country: null, timezone: "UTC", price_currency: null, wallet_currency: "USD" as const, eu_only: false, source: "default" as const } }),
  ),
  suggest: vi.fn(async () => ok([])),
  create: vi.fn(async () => ok({ ref: "barberia-cultor-2", name: "Barbería Cultor", status: "active" as const, duplicate_name: true, read_job_id: null })),
};

describe("NewClientButton", () => {
  beforeEach(() => vi.clearAllMocks());

  it("abre el modal, crea y lleva al Panel del cliente con el aviso", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="es">
        <NewClientButton actions={actions} />
      </LocaleProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Nuevo cliente" }));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo cliente" });
    await user.type(within(dialog).getByRole("textbox", { name: /Nombre/ }), "Barbería Cultor");
    await user.type(within(dialog).getByRole("textbox", { name: /Nicho/ }), "Barbería");
    await user.click(within(dialog).getByRole("button", { name: "Crear cliente" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/clients/barberia-cultor-2"));
    expect(toast.success).toHaveBeenCalledWith("Barbería Cultor creado.");
    // Nombre repetido: avisa, no bloquea (requisito 4.6).
    expect(toast).toHaveBeenCalledWith(expect.stringContaining("barberia-cultor-2"));
  });

  it("llegando con ?new=1 se abre solo, y al cerrarlo la URL vuelve a la lista", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="es">
        <NewClientButton autoOpen actions={actions} />
      </LocaleProvider>,
    );
    const dialog = await screen.findByRole("dialog", { name: "Nuevo cliente" });
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(nav.replace).toHaveBeenCalledWith("/clients");
  });
});
