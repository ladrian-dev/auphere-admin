import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { renameMachineAction, archiveMachineAction, linkClientAction, unlinkClientAction } = await import("../actions");

describe("partner workstation actions (spec 016, R8)", () => {
  it("builder pairs: rename, archive, link and unlink", async () => {
    h.setRole("builder");
    h.backend.renameMachine.mockResolvedValueOnce({ id: "m1", display_name: "Mac" });
    expect(await renameMachineAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", display_name: " Mac " })).toEqual({ ok: true, data: { id: "m1", display_name: "Mac" } });
    expect(h.backend.renameMachine).toHaveBeenCalledWith("7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", "Mac");
    expect(await linkClientAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", ref: "demo" })).toMatchObject({ ok: true });
    expect(await unlinkClientAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", ref: "demo" })).toEqual({ ok: true, data: null });
    expect(await archiveMachineAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual({ ok: true, data: null });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/workstation");
  });
  it("analyst: denied before any call", async () => {
    h.setRole("analyst");
    const fns = [h.backend.renameMachine, h.backend.archiveMachine, h.backend.linkClient, h.backend.unlinkClient];
    for (const fn of fns) fn.mockClear();
    expect(await renameMachineAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", display_name: "x" })).toEqual(h.denied());
    expect(await archiveMachineAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    expect(await linkClientAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", ref: "demo" })).toEqual(h.denied());
    expect(await unlinkClientAction({ id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", ref: "demo" })).toEqual(h.denied());
    for (const fn of fns) expect(fn).not.toHaveBeenCalled();
  });
});
