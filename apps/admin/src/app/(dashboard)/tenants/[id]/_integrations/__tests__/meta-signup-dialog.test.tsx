import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MetaWhatsAppSetupDialog } from "../meta-signup-dialog";

type Envelope = { code: string; waba_id: string; phone_number_id?: string; business_id?: string };

const login = vi.fn<(configId: string, mode: string, version?: string, signal?: AbortSignal) => Promise<Envelope>>();
const connect = vi.fn();

vi.mock("@/lib/meta-fb-sdk", () => ({
  META_CONFIG_ID_CLOUD_API: "cfg-cloud",
  META_CONFIG_ID_COEXISTENCE: "cfg-coex",
  loginWithMeta: (configId: string, mode: string, version?: string, signal?: AbortSignal) => login(configId, mode, version, signal),
}));
vi.mock("../setup-actions", () => ({
  connectMetaWhatsAppSetupAction: (...args: unknown[]) => connect(...args),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

/**
 * Spec 047 (30.4, T101) y spec 049 (7.2, enmienda del 2026-11-26): en el
 * panel, la espera de la ventana de Meta también se cancela, con «Cancelar»,
 * Escape o la ×. Lo que Meta devuelva a un intento cancelado no conecta nada.
 * Mientras el backend conecta el número, no se cancela.
 */
describe("panel: conectar WhatsApp con Meta, la espera se puede cancelar (047 T101; 049 7.2)", () => {
  const signals: Array<AbortSignal | undefined> = [];
  const late: Array<(v: Envelope) => void> = [];

  beforeEach(() => {
    signals.length = 0;
    late.length = 0;
    connect.mockReset();
    login.mockReset();
    login.mockImplementation((_configId, _mode, _version, signal) => {
      signals.push(signal);
      return new Promise<Envelope>((resolve) => late.push(resolve));
    });
  });

  async function openAndStart() {
    const user = userEvent.setup();
    render(<MetaWhatsAppSetupDialog tenantId="tnt_1" alreadyConnected={false} />);
    await user.click(screen.getByRole("button", { name: "Conectar" }));
    const dialog = await screen.findByRole("dialog", { name: "Conectar canal de WhatsApp" });
    await user.click(within(dialog).getAllByRole("button", { name: "Empezar" })[0]!);
    return { user, dialog };
  }

  it("«Cancelar» deja la espera y vuelve a elegir; lo que Meta mande tarde no llega al backend", async () => {
    const { user, dialog } = await openAndStart();
    expect(login).toHaveBeenCalledWith("cfg-cloud", "cloud_api", undefined, expect.any(AbortSignal));
    expect(within(dialog).getByRole("status")).toHaveTextContent("Continúa en la ventana de Meta");
    // «Empezar» se desactivó con el foco dentro: el foco pasa a «Cancelar».
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Cancelar" })).toHaveFocus());
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(signals[0]?.aborted).toBe(true);
    expect(within(dialog).queryByRole("status")).toBeNull();
    for (const b of within(dialog).getAllByRole("button", { name: "Empezar" })) expect(b).toBeEnabled();

    late[0]!({ code: "LATE", waba_id: "w" });
    await new Promise((r) => setTimeout(r, 0));
    expect(connect).not.toHaveBeenCalled();
  });

  it("Escape cierra el diálogo y cancela la espera", async () => {
    const { user } = await openAndStart();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(signals[0]?.aborted).toBe(true);
  });

  it("la × cierra el diálogo y cancela la espera", async () => {
    const { user, dialog } = await openAndStart();
    await user.click(within(dialog).getByRole("button", { name: /^(Cerrar|Close)$/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(signals[0]?.aborted).toBe(true);
  });

  it("mientras el backend conecta el número no se cancela, ni con Escape", async () => {
    connect.mockImplementation(() => new Promise(() => {}));
    const { user, dialog } = await openAndStart();
    late[0]!({ code: "C0DE", waba_id: "W1" });
    await waitFor(() => expect(connect).toHaveBeenCalledWith("tnt_1", expect.objectContaining({ code: "C0DE", waba_id: "W1", mode: "cloud_api" })));
    expect(within(dialog).queryByRole("button", { name: "Cancelar" })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Conectar canal de WhatsApp" })).toBeInTheDocument();
  });
});
