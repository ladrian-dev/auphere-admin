import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { saveUsageAlertsAction } = await import("../actions");

describe("usage alerts action (spec 016, R8)", () => {
  it("admin saves (usage:manage); builder is denied before any call", async () => {
    h.setRole("admin");
    const body = { cap_messages_month: 1000, recipients: ["ops@example.com"], enabled: true };
    h.backend.setUsageAlerts.mockResolvedValueOnce(body);
    expect(await saveUsageAlertsAction(body)).toEqual({ ok: true, data: body });
    expect(h.backend.setUsageAlerts).toHaveBeenCalledWith(body);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/usage/alerts");
    h.setRole("builder");
    h.backend.setUsageAlerts.mockClear();
    expect(await saveUsageAlertsAction({ cap_messages_month: null, recipients: [], enabled: false })).toEqual(h.denied());
    expect(h.backend.setUsageAlerts).not.toHaveBeenCalled();
  });
});
