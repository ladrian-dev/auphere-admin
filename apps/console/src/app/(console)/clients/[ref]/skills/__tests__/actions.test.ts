import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { saveSkillsAction } = await import("../actions");

describe("skills actions (spec 016, R8)", () => {
  it("builder saves; analyst is denied before any call", async () => {
    h.setRole("builder");
    h.backend.putSkills.mockResolvedValueOnce({ version: 2 });
    expect(await saveSkillsAction({ ref: "demo", skills: ["booking_reminders"] })).toEqual({ ok: true, data: { version: 2 } });
    expect(h.backend.putSkills).toHaveBeenCalledWith("demo", ["booking_reminders"]);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
    h.setRole("analyst");
    h.backend.putSkills.mockClear();
    expect(await saveSkillsAction({ ref: "demo", skills: [] })).toEqual(h.denied());
    expect(h.backend.putSkills).not.toHaveBeenCalled();
  });
});
