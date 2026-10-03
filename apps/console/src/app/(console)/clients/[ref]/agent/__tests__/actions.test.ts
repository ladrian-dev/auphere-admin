import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { saveModelAction, saveAgentSettingsAction } = await import("../actions");

describe("agent actions (spec 016, R5.2 + R8)", () => {
  it("saveModelAction writes the binding and revalidates the agent layout", async () => {
    h.setRole("builder");
    const out = { client_ref: "demo", role: "respond", model_id: "openai/gpt-5.6-luna", display_name: "Luna", is_bound: true, allowed: true, fallback_model_id: "openai/gpt-5.6-sol", fallback_display_name: "Sol" };
    h.backend.setClientModel.mockResolvedValueOnce(out);
    expect(await saveModelAction({ ref: "demo", model_id: "openai/gpt-5.6-luna" })).toEqual({ ok: true, data: out });
    expect(h.backend.setClientModel).toHaveBeenCalledWith("demo", "openai/gpt-5.6-luna");
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/agent", "layout");
  });
  it("saveModelAction hands unknown_model to the screen as a code", async () => {
    h.setRole("owner");
    h.fail("setClientModel", 422, "", "unknown_model");
    expect(await saveModelAction({ ref: "demo", model_id: "x" })).toMatchObject({ ok: false, status: 422, code: "unknown_model" });
  });
  it("saveModelAction and saveAgentSettingsAction are denied without agents:write, before any call", async () => {
    h.setRole("analyst");
    h.backend.setClientModel.mockClear();
    h.backend.putAgentSettings.mockClear();
    expect(await saveModelAction({ ref: "demo", model_id: "openai/gpt-5.6-luna" })).toEqual(h.denied());
    expect(await saveAgentSettingsAction({ ref: "demo", settings: {} })).toEqual(h.denied());
    expect(h.backend.setClientModel).not.toHaveBeenCalled();
    expect(h.backend.putAgentSettings).not.toHaveBeenCalled();
  });
});
