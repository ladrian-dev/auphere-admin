import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { createClientAction, updateClientAction, setClientStatusAction, deleteClientAction, stageAgentAction, publishAgentAction, rollbackAgentAction } = await import("../actions");

describe("client actions (spec 016, R8 — the seven of Bloque A11)", () => {
  it("builder: create, update, status and the agent versions", async () => {
    h.setRole("builder");
    h.backend.createClient.mockResolvedValueOnce({ external_client_ref: "demo" });
    expect(await createClientAction({ external_client_ref: "demo", name: "Demo", timezone: "UTC" })).toMatchObject({ ok: true });
    expect(await updateClientAction({ ref: "demo", name: "Demo 2" })).toMatchObject({ ok: true });
    expect(h.backend.updateClient).toHaveBeenCalledWith("demo", { name: "Demo 2" });
    expect(await setClientStatusAction({ ref: "demo", status: "paused" })).toMatchObject({ ok: true });
    expect(await stageAgentAction({ ref: "demo", system_prompt: "You are…" })).toMatchObject({ ok: true });
    expect(await publishAgentAction({ ref: "demo", version: 1 })).toMatchObject({ ok: true });
    expect(await rollbackAgentAction({ ref: "demo", version: 1 })).toMatchObject({ ok: true });
    expect(h.backend.rollbackAgentVersion).toHaveBeenCalledWith("demo", 1);
  });
  it("delete needs clients:delete: builder is denied, admin is not", async () => {
    h.setRole("builder");
    h.backend.deleteClient.mockClear();
    expect(await deleteClientAction({ ref: "demo", confirm_name: "Demo" })).toEqual(h.denied());
    expect(h.backend.deleteClient).not.toHaveBeenCalled();
    h.setRole("admin");
    h.backend.deleteClient.mockResolvedValueOnce(null);
    expect(await deleteClientAction({ ref: "demo", confirm_name: "Demo" })).toEqual({ ok: true, data: null });
    expect(h.backend.deleteClient).toHaveBeenCalledWith("demo", "Demo");
  });
  it("analyst: every write is denied before any call", async () => {
    h.setRole("analyst");
    const fns = [h.backend.createClient, h.backend.updateClient, h.backend.setClientStatus, h.backend.deleteClient, h.backend.stageAgentVersion, h.backend.publishAgentVersion, h.backend.rollbackAgentVersion];
    for (const fn of fns) fn.mockClear();
    expect(await createClientAction({ external_client_ref: "demo", name: "Demo", timezone: "UTC" })).toEqual(h.denied());
    expect(await updateClientAction({ ref: "demo", name: "x" })).toEqual(h.denied());
    expect(await setClientStatusAction({ ref: "demo", status: "active" })).toEqual(h.denied());
    expect(await deleteClientAction({ ref: "demo", confirm_name: "Demo" })).toEqual(h.denied());
    expect(await stageAgentAction({ ref: "demo", system_prompt: "x" })).toEqual(h.denied());
    expect(await publishAgentAction({ ref: "demo", version: 1 })).toEqual(h.denied());
    expect(await rollbackAgentAction({ ref: "demo", version: 1 })).toEqual(h.denied());
    for (const fn of fns) expect(fn).not.toHaveBeenCalled();
  });
});
