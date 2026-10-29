import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WhatsAppPinDialog } from "../whatsapp-pin-dialog";

const rotate = vi.fn();
vi.mock("../setup-actions", () => ({
  rotateWhatsAppPinAction: (tenantId: string, channelId: string) => rotate(tenantId, channelId),
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

describe("WhatsAppPinDialog (spec 050)", () => {
  beforeEach(() => {
    rotate.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
  });

  it("asks first, then rotates the PIN of that channel without showing it", async () => {
    rotate.mockResolvedValue({ ok: true, data: null });
    const user = userEvent.setup();
    render(<WhatsAppPinDialog tenantId="t1" channelId="c1" />);

    await user.click(screen.getByRole("button", { name: "Rotar PIN" }));
    expect(screen.getByText(/lo guarda cifrado/i)).toBeInTheDocument();
    expect(rotate).not.toHaveBeenCalled();

    const buttons = screen.getAllByRole("button", { name: "Rotar PIN" });
    await user.click(buttons[buttons.length - 1]!);
    expect(rotate).toHaveBeenCalledWith("t1", "c1");
    expect(toastSuccess).toHaveBeenCalledWith("PIN rotado y guardado.");
  });

  it("says in words why Meta or the API refused", async () => {
    rotate.mockResolvedValue({ ok: false, error: "meta_refused_the_pin" });
    const user = userEvent.setup();
    render(<WhatsAppPinDialog tenantId="t1" channelId="c1" />);

    await user.click(screen.getByRole("button", { name: "Rotar PIN" }));
    const buttons = screen.getAllByRole("button", { name: "Rotar PIN" });
    await user.click(buttons[buttons.length - 1]!);
    expect(toastError).toHaveBeenCalledWith("Meta no aceptó el PIN nuevo. El anterior sigue vigente.");
  });
});
