import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { startCheckoutAction, buyCreditAction, openPortalAction, cancelSubscriptionAction } = await import("../actions");

describe("billing actions (spec 016, R8)", () => {
  it("the billing role manages plans, credit, portal and cancellation", async () => {
    h.setRole("billing");
    h.backend.startCheckout.mockResolvedValueOnce({ url: null });
    expect(await startCheckoutAction({ tier_code: "pro" })).toEqual({ ok: true, data: { url: null } });
    expect(h.backend.startCheckout).toHaveBeenCalledWith("pro");
    h.backend.buyCredit.mockResolvedValueOnce({ url: "https://pay" });
    expect(await buyCreditAction({ amount_cents: 2_000 })).toMatchObject({ ok: true });
    expect(h.backend.buyCredit).toHaveBeenCalledWith(2_000);
    h.backend.billingPortal.mockResolvedValueOnce({ url: "https://portal" });
    expect(await openPortalAction()).toEqual({ ok: true, data: { url: "https://portal" } });
    expect(await cancelSubscriptionAction()).toMatchObject({ ok: true });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/billing");
  });
  it("admin (no billing:manage): every action is denied before any call", async () => {
    h.setRole("admin");
    const fns = [h.backend.startCheckout, h.backend.buyCredit, h.backend.billingPortal, h.backend.cancelSubscription];
    for (const fn of fns) fn.mockClear();
    expect(await startCheckoutAction({ tier_code: "team" })).toEqual(h.denied());
    expect(await buyCreditAction({ amount_cents: 500 })).toEqual(h.denied());
    expect(await openPortalAction()).toEqual(h.denied());
    expect(await cancelSubscriptionAction()).toEqual(h.denied());
    for (const fn of fns) expect(fn).not.toHaveBeenCalled();
  });
  it("the amount limits are the API's (500..500000 cents)", async () => {
    h.setRole("owner");
    await expect(buyCreditAction({ amount_cents: 499 })).rejects.toThrow();
    await expect(buyCreditAction({ amount_cents: 500_001 })).rejects.toThrow();
  });
});
