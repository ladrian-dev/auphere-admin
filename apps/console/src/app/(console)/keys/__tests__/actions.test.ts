import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { createKeyAction, rotateKeyAction, revokeKeyAction } = await import("../actions");

describe("keys actions (spec 016, R8)", () => {
  it("owner: create, rotate, revoke reach the backend and revalidate", async () => {
    h.setRole("owner");
    h.backend.createKey.mockResolvedValueOnce({ id: "k1" });
    expect(await createKeyAction({ type: "live", scopes: ["provision"] })).toEqual({ ok: true, data: { id: "k1" } });
    expect(h.backend.createKey).toHaveBeenCalledWith({ type: "live", scopes: ["provision"] });
    h.backend.rotateKey.mockResolvedValueOnce({ id: "k2" });
    expect(await rotateKeyAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(h.backend.rotateKey).toHaveBeenCalledWith("7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", 24);
    h.backend.revokeKey.mockResolvedValueOnce({ id: "k1", revoked_at: "x" });
    expect(await revokeKeyAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject({ ok: true });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/keys");
  });
  it("builder (keys:read only): every write is denied before any call", async () => {
    h.setRole("builder");
    for (const fn of [h.backend.createKey, h.backend.rotateKey, h.backend.revokeKey]) fn.mockClear();
    expect(await createKeyAction({ type: "test", scopes: ["broadcasts"] })).toEqual(h.denied());
    expect(await rotateKeyAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    expect(await revokeKeyAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    for (const fn of [h.backend.createKey, h.backend.rotateKey, h.backend.revokeKey]) expect(fn).not.toHaveBeenCalled();
  });
});
