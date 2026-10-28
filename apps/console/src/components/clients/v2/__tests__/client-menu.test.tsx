import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ClientDetailV2 } from "@/lib/backend/client-records";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  archiveClientAction: vi.fn(),
  deleteClientV2Action: vi.fn(),
  getClientV2Action: vi.fn(),
  restoreClientAction: vi.fn(),
  updateClientV2Action: vi.fn(),
}));
vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  createClientV2Action: vi.fn(),
  detectClientLinksAction: vi.fn(async () => ({
    ok: true,
    data: { links: [], deduced: { country: "ES", timezone: "Europe/Madrid", price_currency: "EUR", wallet_currency: "USD", eu_only: true, source: "default" } },
  })),
  nicheSuggestionsAction: vi.fn(async () => ({ ok: true, data: [] })),
}));

const { ClientMenu, editBody } = await import("../client-menu");

/**
 * Spec 047 (T063, historia 14) con el prototipo aprobado (`clientes.md` §2.3,
 * 7.4 y D4): el menú ⋯ del cliente. Archivar no pregunta: se hace al momento y
 * el aviso trae «Deshacer», que restaura; eliminar pide escribir el nombre y
 * dice la razón legal cuando no se puede; editar abre el modal del alta con lo
 * de hoy y guarda con la revisión leída.
 */
const ok = <T,>(data: T) => ({ ok: true as const, data });
const lifecycle = { ref: "barberia-cultor", lifecycle: "archived" as const, previous: "active" as const, agents: [], undo: "restore" as const };
const DETAIL: ClientDetailV2 = {
  external_client_ref: "barberia-cultor",
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  niche: "Barbería de barrio",
  info: "Desde 1998",
  website: null,
  country: "ES",
  price_currency: "EUR",
  wallet_currency: "USD",
  eu_only: true,
  lifecycle: "active",
  revision: 4,
  allowed: ["edit", "assign_balance", "new_agent", "archive", "delete"],
};

function menu(actions: Record<string, unknown>, allowed = DETAIL.allowed) {
  return render(
    <LocaleProvider locale="es">
      <ClientMenu refId="barberia-cultor" name="Barbería Cultor" allowed={allowed} detail={DETAIL} actions={actions} />
    </LocaleProvider>,
  );
}

describe("ClientMenu", () => {
  beforeEach(() => vi.clearAllMocks());

  it("archivar no pregunta: archiva al momento y el aviso trae «Deshacer», que restaura (escenario 3)", async () => {
    const user = userEvent.setup();
    const archive = vi.fn(async () => ok(lifecycle));
    const restore = vi.fn(async () => ok({ ...lifecycle, lifecycle: "active" as const, undo: null }));
    menu({ archive, restore });
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    expect(await axeViolations()).toEqual([]);
    await user.click(await screen.findByRole("menuitem", { name: "Archivar" }));
    expect(screen.queryByRole("dialog", { name: "Archivar Barbería Cultor" })).toBeNull();
    await waitFor(() => expect(archive).toHaveBeenCalledWith({ ref: "barberia-cultor" }));
    expect(toast.success).toHaveBeenCalledWith("Barbería Cultor archivado. Sus agentes quedan en pausa.", expect.objectContaining({ action: expect.anything() }));
    const [, options] = toast.success.mock.calls[0] as [string, { action: { label: string; onClick: () => void } }];
    expect(options.action.label).toBe("Deshacer");
    options.action.onClick();
    await waitFor(() => expect(restore).toHaveBeenCalledWith({ ref: "barberia-cultor" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("eliminar pide el nombre y dice la razón legal si no se puede (escenario 5)", async () => {
    const user = userEvent.setup();
    const remove = vi.fn(async () => ({ ok: false as const, status: 409, message: "x", code: "legal_retention" }));
    menu({ remove });
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await user.click(await screen.findByRole("menuitem", { name: "Eliminar…" }));
    const confirm = screen.getByRole("button", { name: "Eliminar para siempre" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    await user.type(screen.getByRole("textbox"), "Barbería Cultor");
    await user.click(confirm);
    await waitFor(() => expect(remove).toHaveBeenCalledWith({ ref: "barberia-cultor", confirm_name: "Barbería Cultor" }));
    expect(await screen.findByText(/aparece en una factura o tiene pagos anotados/)).toBeTruthy();
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("editar abre el modal del alta con lo de hoy y guarda con la revisión leída", async () => {
    const user = userEvent.setup();
    const update = vi.fn(async () => ok({ ...DETAIL, name: "Cultor Centro", revision: 5 }));
    menu({ update });
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await user.click(await screen.findByRole("menuitem", { name: "Editar cliente" }));
    const name = await screen.findByLabelText(/Nombre/);
    expect((name as HTMLInputElement).value).toBe("Barbería Cultor");
    await user.clear(name);
    await user.type(name, "Cultor Centro");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    const [arg] = update.mock.calls[0] as unknown as [{ revision: number; body: Record<string, unknown> }];
    expect(arg.revision).toBe(4);
    expect(arg.body.name).toBe("Cultor Centro");
    expect(arg.body).not.toHaveProperty("links");
    expect(toast.success).toHaveBeenCalledWith("Cambios guardados. Sus agentes ya los usan.");
  });

  it("con iconos, sin «Nuevo agente» y con el separador antes de archivar (prototipo §2.3)", async () => {
    const user = userEvent.setup();
    menu({});
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await screen.findByRole("menuitem", { name: "Editar cliente" });
    const menuEl = screen.getByRole("menu");
    const order = Array.from(menuEl.querySelectorAll("[role=menuitem], [role=separator]")).map((el) =>
      el.getAttribute("role") === "separator" ? "—" : el.textContent,
    );
    expect(order).toEqual(["Editar cliente", "Asignar saldo", "—", "Archivar", "Eliminar…"]);
    for (const item of screen.getAllByRole("menuitem")) expect(item.querySelector("svg")).toBeTruthy();
  });

  it("un archivado ofrece «Restaurar», que restaura sin preguntar", async () => {
    const user = userEvent.setup();
    const restore = vi.fn(async () => ok({ ...lifecycle, lifecycle: "active" as const, undo: null }));
    menu({ restore }, ["edit", "restore", "delete"]);
    await user.click(screen.getByRole("button", { name: "Acciones de Barbería Cultor" }));
    await user.click(await screen.findByRole("menuitem", { name: "Restaurar" }));
    await waitFor(() => expect(restore).toHaveBeenCalledWith({ ref: "barberia-cultor" }));
    expect(toast.success).toHaveBeenCalledWith("Barbería Cultor restaurado. Cada agente vuelve a como estaba.");
  });

  it("sin nada permitido no pinta el menú", () => {
    const { container } = menu({}, []);
    expect(container.querySelector("[data-slot=client-menu]")).toBeNull();
  });

  it("lo que manda el modal al guardar no lleva los chips", () => {
    expect(
      editBody({ name: "A", niche: "Bar", info: "", country: "ES", timezone: "Europe/Madrid", price_currency: "EUR", wallet_currency: "USD", eu_only: true, links: [] }),
    ).toEqual({ name: "A", niche: "Bar", info: "", country: "ES", timezone: "Europe/Madrid", price_currency: "EUR", wallet_currency: "USD", eu_only: true });
  });
});
