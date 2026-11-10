import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { MetaSocialOffer } from "@/lib/backend/channels";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), info: vi.fn() }));
const actions = vi.hoisted(() => ({ metaSocialConnectAction: vi.fn(), metaSocialCompleteAction: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => actions);
vi.mock("@/lib/meta-fb-sdk", async (orig) => ({ ...(await orig<object>()), loginForCode: vi.fn(async () => "CODE") }));

const { useMetaSocialConnect } = await import("../meta-social-connect");

const OFFER: MetaSocialOffer = { app_id: "1", graph_version: "v26.0", channels: [{ kind: "instagram", config_id: "9" }] };

function Harness() {
  const { start, dialog } = useMetaSocialConnect({ refId: "flor", offer: OFFER });
  return (
    <>
      <button type="button" onClick={() => void start("instagram")}>
        go
      </button>
      {dialog}
    </>
  );
}

const mount = () =>
  render(
    <LocaleProvider locale="es">
      <Harness />
    </LocaleProvider>,
  );

beforeEach(() => {
  vi.clearAllMocks();
});

/**
 * QA 2026-10-30 (design audit item 4): Instagram and Messenger end like
 * WhatsApp. A failure stays on screen with «Intentar de nuevo» instead of a
 * toast that goes away, and the account picker can be cancelled, saying
 * nothing was connected.
 */
describe("conectar Instagram o Messenger", () => {
  it("un fallo se queda en pantalla y se puede reintentar", async () => {
    const user = userEvent.setup();
    actions.metaSocialConnectAction.mockResolvedValueOnce({ ok: false, status: 409, message: "x", code: "no_page" });
    actions.metaSocialConnectAction.mockResolvedValueOnce({ ok: false, status: 409, message: "x", code: "no_page" });
    mount();
    await user.click(screen.getByRole("button", { name: "go" }));
    expect(await screen.findByText("No se pudo conectar")).toBeInTheDocument();
    expect(screen.getByText(/No se compartió ninguna Página/)).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
    expect(actions.metaSocialConnectAction).toHaveBeenCalledTimes(2);
  });

  it("el selector de cuentas se cancela y dice que no se conectó nada", async () => {
    const user = userEvent.setup();
    actions.metaSocialConnectAction.mockResolvedValueOnce({
      ok: true,
      data: {
        status: "choose",
        channel: null,
        nonce: "n1",
        accounts: [
          { id: "a", name: "Uno", username: "uno.store", picture_url: null },
          { id: "b", name: "Dos", username: "dos.store", picture_url: null },
        ],
      },
    });
    mount();
    await user.click(screen.getByRole("button", { name: "go" }));
    expect(await screen.findByRole("button", { name: /@uno\.store/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(toast.info).toHaveBeenCalledWith("No se conectó nada.");
    expect(actions.metaSocialCompleteAction).not.toHaveBeenCalled();
  });
});
