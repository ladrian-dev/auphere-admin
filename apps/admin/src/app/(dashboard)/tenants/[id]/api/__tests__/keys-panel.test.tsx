import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "sonner";

import type { TenantApiKeyOut } from "@/lib/backend";

import { ApiKeysPanel } from "../keys-panel";

const create = vi.fn();
const rotate = vi.fn();
const revoke = vi.fn();
const refresh = vi.fn();
vi.mock("../actions", () => ({
  createTenantKeyAction: (...a: unknown[]) => create(...a),
  rotateTenantKeyAction: (...a: unknown[]) => rotate(...a),
  revokeTenantKeyAction: (...a: unknown[]) => revoke(...a),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: (...a: unknown[]) => refresh(...a) }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const key = (over: Partial<TenantApiKeyOut> = {}): TenantApiKeyOut => ({
  id: "k1",
  partner_id: "p1",
  tenant_id: "t1",
  type: "live",
  prefix_snippet: "ak_live_8f2a",
  scopes: ["messages_send"],
  created_at: "2026-11-24T10:00:00Z",
  last_used_at: null,
  revoked_at: null,
  grace_expires_at: null,
  expires_at: null,
  created_by: "luis@auphere.com",
  ...over,
});

describe("«Envío por API»: the client's keys (spec 077, 5.1–5.4)", () => {
  beforeEach(() => {
    create.mockReset();
    rotate.mockReset();
    revoke.mockReset();
    refresh.mockReset();
    vi.mocked(toast.success).mockReset();
  });

  it("says when the keys could not be read, instead of an empty list, and retries", async () => {
    const user = userEvent.setup();
    render(<ApiKeysPanel tenantId="t1" tenantName="Tecfin" keys={null} />);
    expect(screen.getByText("No se pudieron leer las claves")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(refresh).toHaveBeenCalled();
  });

  it("a client without keys can create the first from the empty state itself", async () => {
    create.mockResolvedValue({ ok: true, data: { key: key({ id: "k9" }), plaintext: "ak_live_8f2a_secret" } });
    const user = userEvent.setup();
    render(<ApiKeysPanel tenantId="t1" tenantName="Tecfin" keys={[]} />);
    const empty = screen.getByText("Este cliente todavía no tiene claves").closest("[data-slot=empty-state]") as HTMLElement;
    await user.click(within(empty).getByRole("button", { name: "Crear clave" }));
    expect(create).toHaveBeenCalledWith("t1");
  });

  it("lists each key with its state; a revoked one has nothing left to do", () => {
    render(
      <ApiKeysPanel
        tenantId="t1"
        tenantName="Tecfin"
        keys={[key(), key({ id: "k2", prefix_snippet: "ak_live_old", revoked_at: "2026-11-20T00:00:00Z" })]}
      />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).getByText("Activa")).toBeInTheDocument();
    expect(within(rows[0]!).getByRole("button", { name: /Opciones de la clave ak_live_8f2a/ })).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Revocada")).toBeInTheDocument();
    expect(within(rows[1]!).queryByRole("button")).toBeNull();
  });

  it("names who issued each key, and says nothing for one issued outside the panel (R5.1)", () => {
    render(
      <ApiKeysPanel
        tenantId="t1"
        tenantName="Tecfin"
        keys={[key(), key({ id: "k2", prefix_snippet: "ak_live_script", created_by: null })]}
      />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).getByText(/por luis@auphere\.com/)).toBeInTheDocument();
    expect(within(rows[1]!).queryByText(/ por /)).toBeNull();
  });

  it("shows the whole key once, after creating it, and takes focus there (WCAG 4.1.3)", async () => {
    create.mockResolvedValue({ ok: true, data: { key: key({ id: "k9" }), plaintext: "ak_live_8f2a_secret" } });
    const user = userEvent.setup();
    render(<ApiKeysPanel tenantId="t1" tenantName="Tecfin" keys={[]} />);
    await user.click(screen.getAllByRole("button", { name: "Crear clave" })[0]!);
    expect(create).toHaveBeenCalledWith("t1");
    expect(screen.getByText("Copia la clave ahora. No se vuelve a mostrar.")).toBeInTheDocument();
    const input = screen.getByLabelText("Clave nueva");
    expect(input).toHaveValue("ak_live_8f2a_secret");
    expect(input).toHaveFocus();
    expect(input).toHaveAccessibleDescription("Copia la clave ahora. No se vuelve a mostrar.");
    expect(toast.success).toHaveBeenCalledWith("Clave creada", expect.anything());
    expect(screen.getByText(/Clave ak_live_8f2a creada\. Cópiala ahora/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ya la guardé" }));
    expect(screen.queryByLabelText("Clave nueva")).toBeNull();
    // The button that had focus is gone: focus goes to the list, not to <body>.
    expect(screen.getByRole("heading", { name: "Claves de acceso" })).toHaveFocus();
  });

  it("a second key starts with «Copiar», never with the first one's «Copiada»", async () => {
    create
      .mockResolvedValueOnce({ ok: true, data: { key: key({ id: "k9" }), plaintext: "ak_live_first" } })
      .mockResolvedValueOnce({ ok: true, data: { key: key({ id: "k10" }), plaintext: "ak_live_second" } });
    const user = userEvent.setup();
    render(<ApiKeysPanel tenantId="t1" tenantName="Tecfin" keys={[key()]} />);
    await user.click(screen.getByRole("button", { name: "Crear clave" }));
    await user.click(screen.getByRole("button", { name: "Copiar" }));
    expect(await screen.findByRole("button", { name: "Copiada" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Crear clave" }));
    expect(screen.getByLabelText("Clave nueva")).toHaveValue("ak_live_second");
    expect(screen.getByRole("button", { name: "Copiar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copiada" })).toBeNull();
  });

  it("after a rotate, focus lands on the new key", async () => {
    rotate.mockResolvedValue({ ok: true, data: { key: key({ id: "k11" }), plaintext: "ak_live_rotated" } });
    const user = userEvent.setup();
    render(<ApiKeysPanel tenantId="t1" tenantName="Tecfin" keys={[key()]} />);
    await user.click(screen.getByRole("button", { name: /Opciones de la clave ak_live_8f2a/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Rotar…" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Rotar clave" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(rotate).toHaveBeenCalledWith("t1", "k1", 24);
    await waitFor(() => expect(screen.getByLabelText("Clave nueva")).toHaveFocus());
  });

  it("after a revoke, focus goes to the keys heading instead of the menu that disappears", async () => {
    revoke.mockResolvedValue({ ok: true, data: null });
    const user = userEvent.setup();
    render(<ApiKeysPanel tenantId="t1" tenantName="Tecfin" keys={[key()]} />);
    await user.click(screen.getByRole("button", { name: /Opciones de la clave ak_live_8f2a/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Revocar…" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Revocar ahora" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(screen.getByRole("heading", { name: "Claves de acceso" })).toHaveFocus());
  });
});
