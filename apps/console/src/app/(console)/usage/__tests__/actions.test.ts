import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { moveAllocationAction, saveAllocationAction } = await import("../actions");

describe("usage actions (spec 016, R3 + R8)", () => {
  it("moveAllocationAction makes ONE backend call and revalidates", async () => {
    h.setRole("owner");
    const moved = { from: { client_ref: "a", cap: 30_000, remaining: 30_000 }, to: { client_ref: "b", cap: 70_000, remaining: 70_000 } };
    h.backend.moveAllocation.mockResolvedValueOnce(moved);
    const res = await moveAllocationAction({ from_ref: "a", to_ref: "b", qty: 20_000 });
    expect(res).toEqual({ ok: true, data: moved });
    expect(h.backend.moveAllocation).toHaveBeenCalledTimes(1);
    expect(h.backend.moveAllocation).toHaveBeenCalledWith("a", "b", 20_000);
    expect(h.backend.setAllocation).not.toHaveBeenCalled();
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/usage");
  });
  it("moveAllocationAction hands the API's code to the screen", async () => {
    h.setRole("owner");
    h.fail("moveAllocation", 422, "", "insufficient_cap");
    const res = await moveAllocationAction({ from_ref: "a", to_ref: "b", qty: 1 });
    expect(res).toMatchObject({ ok: false, status: 422, code: "insufficient_cap" });
  });
  it("moveAllocationAction is denied without usage:write, before any call", async () => {
    h.setRole("analyst");
    h.backend.moveAllocation.mockClear();
    expect(await moveAllocationAction({ from_ref: "a", to_ref: "b", qty: 1 })).toEqual(h.denied());
    expect(h.backend.moveAllocation).not.toHaveBeenCalled();
  });
  it("saveAllocationAction: allowed for owner, denied for analyst", async () => {
    h.setRole("owner");
    h.backend.setAllocation.mockResolvedValueOnce({ client_ref: "a", cap: 5, remaining: 5 });
    expect(await saveAllocationAction({ client_ref: "a", cap: 5 })).toEqual({ ok: true, data: { client_ref: "a", cap: 5, remaining: 5 } });
    h.setRole("analyst");
    h.backend.setAllocation.mockClear();
    expect(await saveAllocationAction({ client_ref: "a", cap: 5 })).toEqual(h.denied());
    expect(h.backend.setAllocation).not.toHaveBeenCalled();
  });
});
