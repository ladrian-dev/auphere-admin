import { describe, expect, it } from "vitest";

import { DIRECT, sendOnlyPlan, type SendOnlyDraft } from "../send-only-plan";

const draft: SendOnlyDraft = {
  partner: DIRECT,
  requireMembership: false,
  payer: "stripe",
  amount: "40,00",
  email: "",
};

describe("what the wizard saves for a send-only client (spec 077, T024)", () => {
  it("a direct client with no membership saves nothing more", () => {
    expect(sendOnlyPlan(draft)).toEqual({ ok: true, followUp: { partnerId: null, membership: null } });
  });

  it("the partner is saved even without a membership", () => {
    expect(sendOnlyPlan({ ...draft, partner: "p1" })).toEqual({
      ok: true,
      followUp: { partnerId: "p1", membership: null },
    });
  });

  it("a membership by card needs a billing e-mail, and goes in cents", () => {
    expect(sendOnlyPlan({ ...draft, requireMembership: true })).toEqual({
      ok: false,
      errors: { email: expect.any(String) },
    });
    expect(sendOnlyPlan({ ...draft, requireMembership: true, email: " facturacion@tecfin.cl " })).toEqual({
      ok: true,
      followUp: {
        partnerId: null,
        membership: { payer: "stripe", amount_cents: 4000, billing_email: "facturacion@tecfin.cl" },
      },
    });
  });

  it("the partner's balance only exists with a partner, and needs no e-mail", () => {
    const noPartner = sendOnlyPlan({ ...draft, requireMembership: true, payer: "partner_wallet" });
    expect(noPartner.ok).toBe(false);
    expect(sendOnlyPlan({ ...draft, partner: "p1", requireMembership: true, payer: "partner_wallet", amount: "50" })).toEqual({
      ok: true,
      followUp: { partnerId: "p1", membership: { payer: "partner_wallet", amount_cents: 5000, billing_email: null } },
    });
  });

  it("refuses an amount that is not one", () => {
    const res = sendOnlyPlan({ ...draft, requireMembership: true, email: "a@b.co", amount: "cuarenta" });
    expect(res).toEqual({ ok: false, errors: { amount: expect.any(String) } });
  });
});
