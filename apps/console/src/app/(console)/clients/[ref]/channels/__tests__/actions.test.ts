import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { whatsappSignupAction, setChannelRoleAction } = await import("../actions");

const envelope = { ref: "demo", code: "abc", waba_id: "W1", phone_number_id: "PN", mode: "cloud_api" as const };

describe("channels actions (spec 016, R1.1 + R8)", () => {
  it("whatsappSignupAction posts the envelope and revalidates the client layout", async () => {
    h.setRole("owner");
    const out = { status: "connected", channel_id: "c1", display_phone_number: "+34", mode: "cloud_api", used_channels: 1, max_channels: 1, client_status: "active", health: { ready: true, missing: [] } };
    h.backend.whatsappSignup.mockResolvedValueOnce(out);
    const res = await whatsappSignupAction(envelope);
    expect(res).toEqual({ ok: true, data: out });
    expect(h.backend.whatsappSignup).toHaveBeenCalledWith("demo", { code: "abc", waba_id: "W1", phone_number_id: "PN", mode: "cloud_api" });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
  });
  it("whatsappSignupAction hands number_in_use to the screen as a code", async () => {
    h.setRole("owner");
    h.fail("whatsappSignup", 409, "", "number_in_use");
    expect(await whatsappSignupAction(envelope)).toMatchObject({ ok: false, status: 409, code: "number_in_use" });
  });
  it("whatsappSignupAction is denied without channels:write, before any call", async () => {
    h.setRole("analyst");
    h.backend.whatsappSignup.mockClear();
    expect(await whatsappSignupAction(envelope)).toEqual(h.denied());
    expect(h.backend.whatsappSignup).not.toHaveBeenCalled();
  });
  it("setChannelRoleAction: allowed for owner, denied for analyst", async () => {
    h.setRole("owner");
    h.backend.setChannelRole.mockResolvedValueOnce({ id: "c1" });
    expect(await setChannelRoleAction({ ref: "demo", channelId: "0b6d1a2e-6c0e-4d2b-9b7f-3a1f7f6c1234", role: "agent" })).toEqual({ ok: true, data: { id: "c1" } });
    h.setRole("analyst");
    h.backend.setChannelRole.mockClear();
    expect(await setChannelRoleAction({ ref: "demo", channelId: "0b6d1a2e-6c0e-4d2b-9b7f-3a1f7f6c1234", role: "agent" })).toEqual(h.denied());
    expect(h.backend.setChannelRole).not.toHaveBeenCalled();
  });
});
