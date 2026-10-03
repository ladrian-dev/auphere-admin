import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { createThreadAction, patchThreadAction, listThreadsAction, startRunAction, cancelRunAction, getBudgetAction } = await import("../actions");

describe("playground actions (spec 016, R8)", () => {
  it("builder runs the playground", async () => {
    h.setRole("builder");
    h.backend.createPlaygroundThread.mockResolvedValueOnce({ id: "t1" });
    expect(await createThreadAction({ ref: "demo", title: "Prueba" })).toEqual({ ok: true, data: { id: "t1" } });
    expect(h.backend.createPlaygroundThread).toHaveBeenCalledWith("demo", { title: "Prueba" });
    expect(await patchThreadAction({ ref: "demo", thread_id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", archived: true })).toMatchObject({ ok: true });
    expect(await listThreadsAction({ ref: "demo" })).toMatchObject({ ok: true });
    expect(await startRunAction({ ref: "demo", thread_id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", prompt: "hola" })).toMatchObject({ ok: true });
    expect(await cancelRunAction({ ref: "demo", run_id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual({ ok: true, data: null });
    expect(await getBudgetAction()).toMatchObject({ ok: true });
  });
  it("analyst (no playground:run): every action is denied before any call", async () => {
    h.setRole("analyst");
    const fns = [h.backend.createPlaygroundThread, h.backend.patchPlaygroundThread, h.backend.listPlaygroundThreads, h.backend.startPlaygroundRun, h.backend.cancelPlaygroundRun, h.backend.getPlaygroundBudget];
    for (const fn of fns) fn.mockClear();
    const denied = { ok: false, status: 403 };
    expect(await createThreadAction({ ref: "demo" })).toMatchObject(denied);
    expect(await patchThreadAction({ ref: "demo", thread_id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", title: "x" })).toMatchObject(denied);
    expect(await listThreadsAction({ ref: "demo" })).toMatchObject(denied);
    expect(await startRunAction({ ref: "demo", thread_id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d", prompt: "hola" })).toMatchObject(denied);
    expect(await cancelRunAction({ ref: "demo", run_id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toMatchObject(denied);
    expect(await getBudgetAction()).toMatchObject(denied);
    for (const fn of fns) expect(fn).not.toHaveBeenCalled();
  });
});
