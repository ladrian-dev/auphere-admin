import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ClientAccessOut } from "@/lib/backend";

const setAccessAction = vi.fn();
vi.mock("../actions", () => ({
  setAccessAction: (...args: unknown[]) => setAccessAction(...args),
  inviteAction: vi.fn(),
  resendAction: vi.fn(),
  revokeAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const { AccessForm } = await import("../access-form");
const { MembersList } = await import("../members-list");

function access(o: Partial<ClientAccessOut> = {}): ClientAccessOut {
  return {
    eligible: true,
    ineligible_reason: null,
    partner: { id: "p1", name: "Amacrux" },
    whatsapp_connected: false,
    enabled: false,
    modules: [],
    members: [],
    ...o,
  };
}

/** Spec 030 (R1.1, R1.3, R1.9): the operator's access tab. */
describe("AccessForm", () => {
  it("does not let the inbox be chosen without a connected WhatsApp, and says why", () => {
    render(<AccessForm tenantId="t1" access={access()} />);
    const inbox = screen.getByRole("checkbox", { name: /Bandeja de entrada/ });
    // base-ui pinta la casilla como un `span role="checkbox"`: el estado va en atributos.
    expect(inbox.getAttribute("aria-disabled") === "true" || inbox.hasAttribute("data-disabled")).toBe(true);
    expect(screen.getByText(/necesita un WhatsApp conectado/)).toBeTruthy();
  });

  it("cannot save access switched on without modules", async () => {
    render(<AccessForm tenantId="t1" access={access()} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Consola lite encendida/ }));
    const save = screen.getByRole("button", { name: "Guardar acceso" });
    expect(save).toHaveProperty("disabled", true);
    expect(screen.getByText(/Elige al menos un módulo/)).toBeTruthy();
    await userEvent.click(screen.getByRole("checkbox", { name: /^Panel/ }));
    expect(save).toHaveProperty("disabled", false);
  });

  it("sends only what changed, modules in sidebar order", async () => {
    setAccessAction.mockResolvedValue({ ok: true, data: access({ enabled: true, modules: ["panel", "usage"] }) });
    render(<AccessForm tenantId="t1" access={access({ whatsapp_connected: true })} />);
    const save = screen.getByRole("button", { name: "Guardar acceso" });
    expect(save).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("checkbox", { name: /Consola lite encendida/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^Consumo/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /^Panel/ }));
    await userEvent.click(save);
    expect(setAccessAction).toHaveBeenCalledWith("t1", { enabled: true, modules: ["panel", "usage"] });
  });

  it("replaces the form with the reason when the client is not eligible", () => {
    render(<AccessForm tenantId="t1" access={access({ eligible: false, ineligible_reason: "no_partner", partner: null })} />);
    expect(screen.getByText(/no está en ningún partner/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Guardar acceso" })).toBeNull();
  });
});

describe("MembersList", () => {
  it("shows each state and an empty state", () => {
    const { rerender } = render(<MembersList tenantId="t1" members={[]} />);
    expect(screen.getByText("Nadie tiene acceso todavía.")).toBeTruthy();
    rerender(
      <MembersList
        tenantId="t1"
        members={[
          { id: "1", kind: "member", email: "a@x.test", name: "Ana", status: "active", since: "2026-10-01T00:00:00Z", expires_at: null },
          { id: "2", kind: "invitation", email: "b@x.test", name: null, status: "pending", since: null, expires_at: "2026-10-29T00:00:00Z" },
          { id: "3", kind: "invitation", email: "c@x.test", name: null, status: "expired", since: null, expires_at: "2026-09-01T00:00:00Z" },
          { id: "4", kind: "member", email: "d@x.test", name: null, status: "revoked", since: null, expires_at: null },
        ]}
      />,
    );
    expect(screen.getByText("Activa")).toBeTruthy();
    expect(screen.getByText("Invitación pendiente")).toBeTruthy();
    expect(screen.getByText("Invitación caducada")).toBeTruthy();
    expect(screen.getByText("Revocada")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Reenviar/ })).toHaveLength(2);
  });
});
