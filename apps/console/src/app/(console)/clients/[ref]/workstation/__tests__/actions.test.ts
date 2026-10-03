import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { addExecutableAction, archiveExecutableAction } = await import("../actions");

describe("client workstation actions (spec 016, R8)", () => {
  it("admin adds and archives executables (workstation:write)", async () => {
    h.setRole("admin");
    h.backend.addExecutable.mockResolvedValueOnce({ id: "e1", executable: "make" });
    expect(await addExecutableAction({ ref: "demo", executable: "make" })).toEqual({ ok: true, data: { id: "e1", executable: "make" } });
    expect(await archiveExecutableAction({ ref: "demo", id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual({ ok: true, data: null });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/workstation");
  });
  it("builder (pairs, but does not write): denied before any call", async () => {
    h.setRole("builder");
    h.backend.addExecutable.mockClear();
    h.backend.archiveExecutable.mockClear();
    expect(await addExecutableAction({ ref: "demo", executable: "make" })).toEqual(h.denied());
    expect(await archiveExecutableAction({ ref: "demo", id: "7b2a1e3c-4d5f-4a6b-8c7d-9e0f1a2b3c4d" })).toEqual(h.denied());
    expect(h.backend.addExecutable).not.toHaveBeenCalled();
    expect(h.backend.archiveExecutable).not.toHaveBeenCalled();
  });
  it("an executable name is a name, never a path or a shell", async () => {
    h.setRole("admin");
    await expect(addExecutableAction({ ref: "demo", executable: "/bin/sh" })).rejects.toThrow();
    await expect(addExecutableAction({ ref: "demo", executable: "make; rm -rf" })).rejects.toThrow();
  });
});
