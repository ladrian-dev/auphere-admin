import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../agent-model-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const ids = { ref: "demo", agent: AGENT };

/**
 * Spec 065 (T027; requisitos 2.4 y 2.7) — el modelo de un agente desde la
 * consola: leer con `agents:read`, cambiar con `agents:write` (negado antes de
 * llamar a la API), siempre con un modelo (nunca `null`), y los códigos de la
 * API vuelven tal cual.
 */
describe("el modelo de un agente · acciones", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("leer pide el agente de la ruta", async () => {
    h.setRole("analyst");
    await actions.agentModelAction(ids);
    expect(h.backend.getAgentModel).toHaveBeenCalledWith("demo", AGENT);
  });

  it("cambiar manda el modelo y vuelve a pintar la pantalla del agente", async () => {
    await actions.setAgentModelAction({ ...ids, model_id: "openai/gpt-5.6-luna" });
    expect(h.backend.setAgentModel).toHaveBeenCalledWith("demo", AGENT, "openai/gpt-5.6-luna");
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith(`/clients/demo/agents/${AGENT}`);
  });

  it("sin `agents:write` se niega antes de llamar a la API", async () => {
    h.setRole("analyst");
    expect(await actions.setAgentModelAction({ ...ids, model_id: "openai/gpt-5.6-luna" })).toEqual(h.denied());
    expect(h.backend.setAgentModel).not.toHaveBeenCalled();
  });

  it("la consola nunca vuelve al modelo por defecto: `null` no pasa", async () => {
    await expect(actions.setAgentModelAction({ ...ids, model_id: null })).rejects.toThrow();
    await expect(actions.setAgentModelAction({ ...ids, model_id: "" })).rejects.toThrow();
    await expect(actions.setAgentModelAction({ ...ids, agent: "no-es-un-uuid", model_id: "x" })).rejects.toThrow();
    expect(h.backend.setAgentModel).not.toHaveBeenCalled();
  });

  it("los códigos de la API vuelven tal cual", async () => {
    h.fail("setAgentModel", 422, "", "unknown_model");
    expect(await actions.setAgentModelAction({ ...ids, model_id: "x" })).toMatchObject({ ok: false, status: 422, code: "unknown_model" });
    h.fail("setAgentModel", 422, "", "model_unavailable_for_agent");
    expect(await actions.setAgentModelAction({ ...ids, model_id: "x" })).toMatchObject({ ok: false, status: 422, code: "model_unavailable_for_agent" });
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
  });

  it("un usuario de cliente no lee ni cambia el modelo", async () => {
    h.setClient(["panel"]);
    expect(await actions.agentModelAction(ids)).toEqual(h.denied());
    expect(await actions.setAgentModelAction({ ...ids, model_id: "x" })).toEqual(h.denied());
    expect(h.backend.getAgentModel).not.toHaveBeenCalled();
  });
});
