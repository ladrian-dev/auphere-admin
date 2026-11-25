import { describe, expect, it } from "vitest";

import type { MembershipOut } from "@/lib/backend";

import { chargeStatus, membershipView } from "../membership-view";

const NOW = Date.parse("2026-11-24T12:00:00Z");

const base: MembershipOut = {
  tenant_id: "t1",
  payer: "stripe",
  amount_cents: 4000,
  pending_amount_cents: null,
  status: "pending",
  active: false,
  current_period_end: null,
  billing_email: "facturacion@tecfin.cl",
  checkout_url: null,
  checkout_expires_at: null,
  last_synced_at: null,
  last_failure: null,
  partner_id: null,
  partner_name: null,
  has_subscription: false,
};

describe("the membership card (spec 077, T027)", () => {
  it("pending by Stripe without a link: offers to create one, and says the API does not send", () => {
    const v = membershipView(base, NOW);
    expect(v.pill.label).toBe("Pendiente de pago");
    expect(v.sends).toBe(false);
    expect(v.notice).toContain("no envía");
    expect(v.link).toEqual({ kind: "create", label: "Crear enlace de pago" });
    expect(v.canRefresh).toBe(true);
    expect(v.canCharge).toBe(false);
    expect(v.canArchive).toBe(true);
  });

  it("a live link shows with its expiry; an expired one asks for a new one", () => {
    const live = membershipView(
      { ...base, checkout_url: "https://checkout.stripe.com/c/pay/cs_1", checkout_expires_at: "2026-11-25T10:00:00Z" },
      NOW,
    );
    expect(live.link).toEqual({
      kind: "live",
      url: "https://checkout.stripe.com/c/pay/cs_1",
      expiresAt: "2026-11-25T10:00:00Z",
    });
    const expired = membershipView(
      { ...base, checkout_url: "https://checkout.stripe.com/c/pay/cs_1", checkout_expires_at: "2026-11-23T10:00:00Z" },
      NOW,
    );
    expect(expired.link.kind).toBe("expired");
  });

  it("active by Stripe: sends, says when it renews, no link, cannot be removed while the subscription lives", () => {
    const v = membershipView(
      { ...base, status: "active", active: true, has_subscription: true, current_period_end: "2026-12-24T00:00:00Z" },
      NOW,
    );
    expect(v.pill).toEqual({ label: "Activa", tone: "positive" });
    expect(v.sends).toBe(true);
    expect(v.sub).toContain("Se renueva");
    expect(v.link.kind).toBe("none");
    expect(v.amountLocked).not.toBeNull();
    expect(v.canArchive).toBe(false);
    expect(v.canCancel).toBe(true);
  });

  it("follows `active`, not `status`: a wallet membership whose period is over does not send", () => {
    const v = membershipView(
      { ...base, payer: "partner_wallet", status: "active", active: false, current_period_end: "2026-11-20T00:00:00Z" },
      NOW,
    );
    expect(v.sends).toBe(false);
    expect(v.pill.tone).toBe("warning");
    expect(v.notice).toContain("detenidos");
    expect(v.canCharge).toBe(true);
    expect(v.canRefresh).toBe(false);
  });

  it("unpaid from the partner's balance: says why, offers «Cobrar ahora», shows a pending amount", () => {
    const v = membershipView(
      {
        ...base,
        payer: "partner_wallet",
        status: "past_due",
        last_failure: "insufficient_balance",
        pending_amount_cents: 5000,
      },
      NOW,
    );
    expect(v.pill.label).toBe("Impagada");
    expect(v.sub).toContain("el partner no tenía saldo");
    expect(v.notice).toContain("402");
    expect(v.canCharge).toBe(true);
    expect(v.link.kind).toBe("none");
    expect(v.pendingAmount).not.toBeNull();
    expect(v.amountLocked).toBeNull();
  });

  it("canceled: nothing to cancel, can be removed, and Stripe offers a new payment link", () => {
    const v = membershipView({ ...base, status: "canceled" }, NOW);
    expect(v.canCancel).toBe(false);
    expect(v.canArchive).toBe(true);
    expect(v.link.kind).toBe("create");
    expect(v.canCharge).toBe(false);
  });

  it("charges are said in words, and an unknown status passes through", () => {
    expect(chargeStatus("paid").label).toBe("Pagado");
    expect(chargeStatus("failed").tone).toBe("danger");
    expect(chargeStatus("uncollectible").label).toBe("uncollectible");
  });
});
