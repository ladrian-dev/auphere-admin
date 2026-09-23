import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { wizardActivateAction, wizardCreateClientAction, wizardPublishAction, wizardSeedAgentAction, wizardCheckRefAction } = await import("../actions");

describe("wizard actions (spec 016, R4 + R8)", () => {
  it("wizardPublishAction publishes the staged version once, and never again once one is active", async () => {
    h.setRole("owner");
    h.backend.getAgent.mockResolvedValueOnce({ active_version: null, versions: [{ version: 1, status: "staged" }] });
    expect(await wizardPublishAction({ ref: "demo" })).toEqual({ ok: true, data: { published: true, version: 1 } });
    expect(h.backend.publishAgentVersion).toHaveBeenCalledWith("demo", 1);

    h.backend.publishAgentVersion.mockClear();
    h.backend.getAgent.mockResolvedValueOnce({ active_version: 1, versions: [{ version: 1, status: "active" }] });
    expect(await wizardPublishAction({ ref: "demo" })).toEqual({ ok: true, data: { published: false, version: 1 } });
    expect(h.backend.publishAgentVersion).not.toHaveBeenCalled();
  });
  it("wizardActivateAction activates, and leaves an active client alone", async () => {
    h.setRole("owner");
    h.backend.getClient.mockResolvedValueOnce({ external_client_ref: "demo", status: "provisioning" });
    h.backend.setClientStatus.mockResolvedValueOnce({ external_client_ref: "demo", status: "active" });
    expect(await wizardActivateAction({ ref: "demo" })).toEqual({ ok: true, data: { external_client_ref: "demo", status: "active" } });
    expect(h.backend.setClientStatus).toHaveBeenCalledWith("demo", "active");
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo");

    h.backend.setClientStatus.mockClear();
    h.backend.getClient.mockResolvedValueOnce({ external_client_ref: "demo", status: "active" });
    expect(await wizardActivateAction({ ref: "demo" })).toMatchObject({ ok: true });
    expect(h.backend.setClientStatus).not.toHaveBeenCalled();
  });
  it("every stage is denied for the role that cannot do it, before any call", async () => {
    h.setRole("analyst");
    for (const fn of [h.backend.createClient, h.backend.stageAgentFromSeed, h.backend.publishAgentVersion, h.backend.setClientStatus]) fn.mockClear();
    expect(await wizardCreateClientAction({ external_client_ref: "demo", name: "Demo", timezone: "UTC" })).toEqual(h.denied());
    expect(await wizardSeedAgentAction({ ref: "demo", seed_template: "generic_v1", placeholders: {} })).toEqual(h.denied());
    expect(await wizardPublishAction({ ref: "demo" })).toEqual(h.denied());
    expect(await wizardActivateAction({ ref: "demo" })).toEqual(h.denied());
    // Publishing is an agent permission; activating is a client one (R4.3).
    h.setRole("builder");
    h.backend.getAgent.mockResolvedValueOnce({ active_version: 1, versions: [] });
    expect(await wizardPublishAction({ ref: "demo" })).toMatchObject({ ok: true });
    for (const fn of [h.backend.createClient, h.backend.stageAgentFromSeed, h.backend.publishAgentVersion, h.backend.setClientStatus]) expect(fn).not.toHaveBeenCalled();
  });
  it("wizardCheckRefAction: a missing ref lets the wizard continue, an existing one is a 409", async () => {
    h.setRole("owner");
    h.fail("getClient", 404, "Unknown client reference");
    expect(await wizardCheckRefAction({ ref: "new-one" })).toEqual({ ok: true, data: null });
    h.backend.getClient.mockResolvedValueOnce({ external_client_ref: "taken" });
    expect(await wizardCheckRefAction({ ref: "taken" })).toMatchObject({ ok: false, status: 409 });
  });
});
