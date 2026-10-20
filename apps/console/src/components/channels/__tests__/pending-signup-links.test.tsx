/**
 * The WhatsApp link sent to the owner (owner, 2026-10-20): only the one that
 * still works is shown, with until when, and the partner revokes it after
 * confirming. A person who only reads sees it but cannot revoke it.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const revoke = vi.fn();
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  revokeWhatsappSignupLinkAction: (input: { ref: string; id: string }) => revoke(input),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { LocaleProvider } from "@/i18n/client";
import type { SignupLinkRow } from "@/lib/backend/channels";

import { PendingSignupLinks } from "../pending-signup-links";

const LIVE: SignupLinkRow = {
  id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d",
  mode: "coexistence",
  state: "valid",
  created_at: "2026-10-20T10:00:00Z",
  expires_at: "2026-10-27T10:00:00Z",
  consumed_at: null,
};
const OLD: SignupLinkRow = { ...LIVE, id: "8b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", state: "revoked" };

function paint(links: SignupLinkRow[], manage = true) {
  return render(
    <LocaleProvider locale="es">
      <PendingSignupLinks refId="panaderia" links={links} manage={manage} />
    </LocaleProvider>,
  );
}

describe("el enlace de WhatsApp enviado al cliente", () => {
  beforeEach(() => {
    revoke.mockReset();
    revoke.mockResolvedValue({ ok: true, data: null });
  });

  it("solo enseña el que sigue sirviendo", () => {
    paint([LIVE, OLD]);
    expect(screen.getAllByRole("button", { name: "Anular enlace" })).toHaveLength(1);
    expect(screen.getByText(/Hay un enlace sin usar/)).toBeInTheDocument();
  });

  it("sin enlaces vivos no pinta nada", () => {
    const { container } = paint([OLD]);
    expect(container).toBeEmptyDOMElement();
  });

  it("se anula después de confirmar", async () => {
    paint([LIVE]);
    await userEvent.click(screen.getByRole("button", { name: "Anular enlace" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Anular enlace" }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith({ ref: "panaderia", id: LIVE.id }));
  });

  it("quien solo lee lo ve pero no lo anula", () => {
    paint([LIVE], false);
    expect(screen.getByText(/Hay un enlace sin usar/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
