import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../life-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const OTHER = "33333333-3333-4333-8333-333333333333";
const CH = "44444444-4444-4444-8444-444444444441";
const TEST = "77777777-7777-4777-8777-000000000002";
const ids = { ref: "demo", agent: AGENT };

/**
 * Spec 047 (T124, T099) — las acciones de la vida del agente y del copiloto:
 * `agents:write` para renombrar, pausar, reanudar, archivar, restaurar, el
 * agente por defecto y «Arreglar»; el copiloto contesta con `agents:read`
 * (19.5). Los códigos de la API vuelven tal cual.
 */
describe("la vida del agente y el copiloto", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("pausar manda la confirmación solo si se dio, y su negativa vuelve con las conversaciones", async () => {
    await actions.pauseAgentAction(ids);
    expect(h.backend.pauseAgent).toHaveBeenLastCalledWith("demo", AGENT, {});
    await actions.pauseAgentAction({ ...ids, confirm: true });
    expect(h.backend.pauseAgent).toHaveBeenLastCalledWith("demo", AGENT, { confirm: true });
    h.fail("pauseAgent", 409, "", "confirm_required", { open_conversations: 3 });
    expect(await actions.pauseAgentAction(ids)).toMatchObject({ ok: false, code: "confirm_required", info: { open_conversations: 3 } });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
  });

  it("archivar con el destino de cada número; renombrar, restaurar y el agente por defecto", async () => {
    await actions.archiveAgentWithAction({ ...ids, channels: [{ channel_id: CH, to: "pause" }] });
    expect(h.backend.archiveAgentWith).toHaveBeenCalledWith("demo", AGENT, [{ channel_id: CH, to: "pause" }]);
    await expect(actions.archiveAgentWithAction({ ...ids, channels: [{ channel_id: CH, to: "nadie" }] })).rejects.toThrow();
    h.fail("archiveAgentWith", 409, "", "default_agent_required");
    expect(await actions.archiveAgentWithAction({ ...ids, channels: [] })).toMatchObject({ ok: false, code: "default_agent_required" });
    await actions.renameAgentLifeAction({ ...ids, name: " Cobros " });
    expect(h.backend.updateAgent).toHaveBeenCalledWith("demo", AGENT, { name: "Cobros" });
    await expect(actions.renameAgentLifeAction({ ...ids, name: "x".repeat(41) })).rejects.toThrow();
    await actions.restoreAgentAction(ids);
    expect(h.backend.restoreAgent).toHaveBeenCalledWith("demo", AGENT);
    await actions.setDefaultAgentAction({ ...ids, agent: OTHER });
    expect(h.backend.setDefaultAgent).toHaveBeenCalledWith("demo", OTHER);
  });

  it("el copiloto lleva su contexto, y «Arreglar» su alcance", async () => {
    await actions.copilotAction({ ...ids, message: "¿por qué?", context: { test_id: TEST } });
    expect(h.backend.askCopilot).toHaveBeenCalledWith("demo", AGENT, "¿por qué?", { test_id: TEST });
    await actions.copilotFixAction({ ...ids, test: TEST, scope: "business", value: "Cerrado los domingos" });
    expect(h.backend.copilotFix).toHaveBeenCalledWith("demo", AGENT, { test_id: TEST, scope: "business", value: "Cerrado los domingos" });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo/business");
  });

  it("un analista pregunta al copiloto y lee la cabecera, pero no cambia nada", async () => {
    h.setRole("analyst");
    expect(await actions.copilotAction({ ...ids, message: "¿por qué?" })).toMatchObject({ ok: true });
    expect(await actions.agentHeaderAction(ids)).toMatchObject({ ok: true });
    for (const write of [
      actions.pauseAgentAction(ids),
      actions.resumeAgentAction(ids),
      actions.archiveAgentWithAction({ ...ids, channels: [] }),
      actions.restoreAgentAction(ids),
      actions.setDefaultAgentAction(ids),
      actions.renameAgentLifeAction({ ...ids, name: "Otro" }),
      actions.copilotFixAction({ ...ids, test: TEST, scope: "agent", value: "x" }),
    ]) {
      expect(await write).toEqual(h.denied());
    }
    expect(h.backend.pauseAgent).not.toHaveBeenCalled();
    expect(h.backend.copilotFix).not.toHaveBeenCalled();
  });
});
