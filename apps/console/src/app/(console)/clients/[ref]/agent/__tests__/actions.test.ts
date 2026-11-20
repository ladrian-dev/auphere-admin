import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../actions");
const { saveAgentSettingsAction } = actions;

/**
 * Spec 016 (R8). El modelo del cliente (R5.2, `saveModelAction`) salió con la
 * spec 065 (9.3 y 12.4): el modelo es de cada agente y se elige en Agente ›
 * Avanzado (`agents/agent-model-actions.ts`).
 */
describe("agent actions (spec 016, R8)", () => {
  it("saveAgentSettingsAction is denied without agents:write, before any call", async () => {
    h.setRole("analyst");
    h.backend.putAgentSettings.mockClear();
    expect(await saveAgentSettingsAction({ ref: "demo", settings: {} })).toEqual(h.denied());
    expect(h.backend.putAgentSettings).not.toHaveBeenCalled();
  });

  it("the client's model can no longer be set from this tab (spec 065, 9.3)", () => {
    expect("saveModelAction" in actions).toBe(false);
  });
});
