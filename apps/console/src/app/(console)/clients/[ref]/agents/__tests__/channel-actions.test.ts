import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const actions = await import("../channel-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const OTHER = "33333333-3333-4333-8333-333333333333";
const CH = "44444444-4444-4444-8444-444444444441";
const LINK = "55555555-5555-4555-8555-555555555555";
const ids = { ref: "demo", channel: CH };

const CONFIG = {
  audience: { mode: "team_only" as const, test_numbers: ["+34611204893"], exceptions: [] },
  escalation: { recipients: [{ name: "Marta", via: "whatsapp" as const, phone_e164: "+34600000009" }], summary: true },
  wait_message: null,
};

/**
 * Spec 047 (historias 10 y 11; T111, T112, T114 y T115) — las acciones de la
 * página de un canal, su ⋯ y el enlace del dueño: `channels:read` para leer,
 * `channels:write` para lo demás. La revisión viaja con el guardado y los
 * códigos de la API vuelven tal cual (`revision_conflict` con `current` y
 * `changes`, `bag_empty` con su `fix`, `link_pending_exists` con `link_id`).
 */
describe("la página de un canal y su ⋯", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("guardar manda la configuración con la revisión leída; el conflicto vuelve con lo que cambió", async () => {
    await actions.saveChannelConfigAction({ ...ids, revision: 3, config: CONFIG });
    expect(h.backend.saveChannelConfig).toHaveBeenCalledWith("demo", CH, 3, CONFIG);
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
    h.fail("saveChannelConfig", 412, "", "revision_conflict", { current: 5, changes: ["audience"] });
    expect(await actions.saveChannelConfigAction({ ...ids, revision: 3, config: CONFIG })).toMatchObject({
      ok: false,
      status: 412,
      code: "revision_conflict",
      info: { current: 5, changes: ["audience"] },
    });
    h.fail("saveChannelConfig", 409, "", "bag_empty", { fix: "assign_balance" });
    expect(await actions.saveChannelConfigAction({ ...ids, revision: 3, config: CONFIG })).toMatchObject({ code: "bag_empty", info: { fix: "assign_balance" } });
  });

  it("una forma que no es la del contrato no llega a la API", async () => {
    await expect(actions.saveChannelConfigAction({ ...ids, revision: 3, config: { ...CONFIG, audience: { ...CONFIG.audience, mode: "all" } } })).rejects.toThrow();
    await expect(actions.saveChannelConfigAction({ ...ids, config: CONFIG })).rejects.toThrow();
    await expect(actions.moveChannelAction({ ...ids, to: "nadie" })).rejects.toThrow();
    expect(h.backend.saveChannelConfig).not.toHaveBeenCalled();
  });

  it("deshacer, el historial, pasar a otro agente, pausar y reanudar", async () => {
    h.fail("undoChannelConfig", 409, "", "undo_window_closed");
    expect(await actions.undoChannelConfigAction(ids)).toMatchObject({ ok: false, code: "undo_window_closed" });
    await actions.channelHistoryAction(ids);
    expect(h.backend.getChannelHistory).toHaveBeenCalledWith("demo", CH);
    await actions.moveChannelAction({ ...ids, to: OTHER });
    expect(h.backend.moveChannel).toHaveBeenCalledWith("demo", CH, OTHER);
    await actions.pauseChannelAction(ids);
    expect(h.backend.pauseChannel).toHaveBeenCalledWith("demo", CH);
    await actions.resumeChannelAction(ids);
    expect(h.backend.resumeChannel).toHaveBeenCalledWith("demo", CH);
  });

  it("el enlace del dueño: crear, «Revocar y crear» y revocar", async () => {
    await actions.createOwnerLinkAction({ ref: "demo", agent: AGENT, mode: "coexistence" });
    expect(h.backend.createOwnerLink).toHaveBeenLastCalledWith("demo", AGENT, { mode: "coexistence" });
    h.fail("createOwnerLink", 409, "", "link_pending_exists", { link_id: LINK });
    expect(await actions.createOwnerLinkAction({ ref: "demo", agent: AGENT, mode: "cloud_api" })).toMatchObject({
      code: "link_pending_exists",
      info: { link_id: LINK },
    });
    await actions.createOwnerLinkAction({ ref: "demo", agent: AGENT, mode: "whatsapp_login", replace: true });
    expect(h.backend.createOwnerLink).toHaveBeenLastCalledWith("demo", AGENT, { mode: "whatsapp_login", replace: true });
    await expect(actions.createOwnerLinkAction({ ref: "demo", agent: AGENT, mode: "sms" })).rejects.toThrow();
    await actions.revokeOwnerLinkAction({ ref: "demo", agent: AGENT, link: LINK });
    expect(h.backend.revokeOwnerLink).toHaveBeenCalledWith("demo", AGENT, LINK);
  });

  it("un analista lee la página y los números, pero no cambia nada", async () => {
    h.setRole("analyst");
    expect(await actions.channelPageAction(ids)).toMatchObject({ ok: true });
    expect(await actions.agentChannelsAction({ ref: "demo", agent: AGENT })).toMatchObject({ ok: true });
    for (const write of [
      actions.saveChannelConfigAction({ ...ids, revision: 3, config: CONFIG }),
      actions.undoChannelConfigAction(ids),
      actions.moveChannelAction({ ...ids, to: OTHER }),
      actions.pauseChannelAction(ids),
      actions.resumeChannelAction(ids),
      actions.createOwnerLinkAction({ ref: "demo", agent: AGENT, mode: "coexistence" }),
      actions.revokeOwnerLinkAction({ ref: "demo", agent: AGENT, link: LINK }),
    ]) {
      expect(await write).toEqual(h.denied());
    }
    expect(h.backend.saveChannelConfig).not.toHaveBeenCalled();
    expect(h.backend.createOwnerLink).not.toHaveBeenCalled();
  });
});
