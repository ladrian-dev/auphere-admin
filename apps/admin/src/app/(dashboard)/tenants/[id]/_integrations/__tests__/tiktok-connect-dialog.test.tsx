import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TikTokConnectDialog } from "../tiktok-connect-dialog";

const authorizeUrlAction = vi.fn();

vi.mock("../setup-actions", () => ({
  tiktokAuthorizeUrlAction: (tenantId: string) => authorizeUrlAction(tenantId),
}));

const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

const TENANT_ID = "tnt_1";

describe("TikTokConnectDialog", () => {
  beforeEach(() => {
    authorizeUrlAction.mockReset();
    toastError.mockReset();
  });

  it("warns about the two constraints before the operator commits", async () => {
    // Both change what the channel is worth, and both surprise anyone who
    // expects the WhatsApp playbook to transfer. They belong in front of the
    // decision, not in a doc nobody opens.
    const user = userEvent.setup();
    render(<TikTokConnectDialog tenantId={TENANT_ID} />);

    await user.click(screen.getByRole("button", { name: /conectar/i }));

    expect(
      screen.getByText(/no puede escribir primero/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/48 horas/i)).toBeInTheDocument();
    expect(screen.getByText(/EEE, Suiza o Reino Unido/i)).toBeInTheDocument();
  });

  it("sends the operator to the URL the backend minted", async () => {
    const user = userEvent.setup();
    authorizeUrlAction.mockResolvedValue({
      ok: true,
      data: { authorize_url: "https://business-api.tiktok.com/portal/auth?state=abc" },
    });
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        get href() {
          return "http://localhost/";
        },
        set href(value: string) {
          assign(value);
        },
      },
    });

    render(<TikTokConnectDialog tenantId={TENANT_ID} />);
    await user.click(screen.getByRole("button", { name: /conectar/i }));
    await user.click(screen.getByRole("button", { name: /ir a tiktok/i }));

    expect(authorizeUrlAction).toHaveBeenCalledWith(TENANT_ID);
    expect(assign).toHaveBeenCalledWith(
      "https://business-api.tiktok.com/portal/auth?state=abc",
    );
  });

  it("surfaces a backend refusal instead of navigating nowhere", async () => {
    const user = userEvent.setup();
    authorizeUrlAction.mockResolvedValue({
      ok: false,
      error: "El canal de TikTok está desactivado en este entorno.",
    });

    render(<TikTokConnectDialog tenantId={TENANT_ID} />);
    await user.click(screen.getByRole("button", { name: /conectar/i }));
    await user.click(screen.getByRole("button", { name: /ir a tiktok/i }));

    expect(toastError).toHaveBeenCalledWith(
      "No se pudo iniciar la autorización",
      expect.objectContaining({
        description: "El canal de TikTok está desactivado en este entorno.",
      }),
    );
  });

  it("labels the trigger Reconectar for an already-connected channel", async () => {
    // Expected to be used regularly: TikTok's refresh token expires after a
    // year and only a human can renew it.
    render(<TikTokConnectDialog tenantId={TENANT_ID} alreadyConnected />);

    expect(
      screen.getByRole("button", { name: /reconectar/i }),
    ).toBeInTheDocument();
  });
});
