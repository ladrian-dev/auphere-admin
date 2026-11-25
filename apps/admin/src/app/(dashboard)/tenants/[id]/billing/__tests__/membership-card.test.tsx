import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MembershipOut } from "@/lib/backend";

import { MembershipCard } from "../membership-card";

const archive = vi.fn();
const refresh = vi.fn();
vi.mock("../membership-actions", () => ({
  archiveMembershipAction: (...a: unknown[]) => archive(...a),
  cancelMembershipAction: vi.fn(),
  chargeMembershipAction: vi.fn(),
  membershipCheckoutAction: vi.fn(),
  putMembershipAction: vi.fn(),
  refreshMembershipAction: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: (...a: unknown[]) => refresh(...a) }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const membership = (over: Partial<MembershipOut> = {}): MembershipOut => ({
  tenant_id: "t1",
  payer: "stripe",
  amount_cents: 4000,
  pending_amount_cents: null,
  status: "pending",
  active: false,
  current_period_end: null,
  billing_email: "facturacion-de-un-correo-muy-largo@tecfin-servicios-financieros.cl",
  checkout_url: "https://checkout.stripe.com/c/pay/first",
  checkout_expires_at: "2099-01-01T00:00:00Z",
  last_synced_at: null,
  last_failure: null,
  partner_id: null,
  partner_name: null,
  has_subscription: false,
  ...over,
});

const card = (state: Parameters<typeof MembershipCard>[0]["state"]) => (
  <MembershipCard tenantId="t1" tenantName="Tecfin" partner={null} state={state} />
);

describe("the membership card (spec 077, T027): its states", () => {
  beforeEach(() => {
    archive.mockReset();
    refresh.mockReset();
  });

  it("a failed read offers to read it again", async () => {
    const user = userEvent.setup();
    render(card({ kind: "error" }));
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(refresh).toHaveBeenCalled();
  });

  it("the billing e-mail is shown whole, never cut", () => {
    render(card({ kind: "ok", membership: membership(), charges: [] }));
    const email = screen.getByText(/facturacion-de-un-correo-muy-largo/);
    expect(email).not.toHaveClass("truncate");
    expect(email).toHaveClass("wrap-anywhere");
  });

  it("without charges it says when they appear; a failed read of them can be retried", async () => {
    const user = userEvent.setup();
    const view = render(card({ kind: "ok", membership: membership(), charges: [] }));
    expect(screen.getByText("Aún no hay cobros")).toBeInTheDocument();
    expect(screen.getByText("Aparecen con el primer cobro.")).toBeInTheDocument();
    view.rerender(card({ kind: "ok", membership: membership(), charges: null }));
    expect(screen.getByText("No se pudieron leer los cobros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(refresh).toHaveBeenCalled();
  });

  it("a new payment link starts with «Copiar enlace», never with the last one's «Copiado»", async () => {
    const user = userEvent.setup();
    const view = render(card({ kind: "ok", membership: membership(), charges: [] }));
    await user.click(screen.getByRole("button", { name: "Copiar enlace" }));
    expect(await screen.findByRole("button", { name: "Copiado" })).toBeInTheDocument();
    view.rerender(
      card({ kind: "ok", membership: membership({ checkout_url: "https://checkout.stripe.com/c/pay/second" }), charges: [] }),
    );
    expect(screen.getByLabelText("Enlace de pago")).toHaveValue("https://checkout.stripe.com/c/pay/second");
    expect(screen.getByRole("button", { name: "Copiar enlace" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copiado" })).toBeNull();
  });

  it("after «Quitar membresía», focus lands on «Exigir membresía» once the page reloads without it", async () => {
    archive.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    const view = render(card({ kind: "ok", membership: membership({ status: "canceled", checkout_url: null }), charges: [] }));
    await user.click(screen.getByRole("button", { name: "Opciones de la membresía" }));
    await user.click(await screen.findByRole("menuitem", { name: "Quitar membresía…" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Quitar membresía" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(archive).toHaveBeenCalledWith("t1");
    // The refresh brings the client without a membership.
    view.rerender(card({ kind: "none" }));
    expect(screen.getByRole("button", { name: "Exigir membresía" })).toHaveFocus();
  });

  it("a client that never had one does not steal focus on load", () => {
    render(card({ kind: "none" }));
    expect(screen.getByRole("button", { name: "Exigir membresía" })).not.toHaveFocus();
  });
});
