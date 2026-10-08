import { describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { archiveAgentAction, assignChannelAgentAction, createAgentAction, renameAgentAction } = await import("../actions");

const AGENT = "22222222-2222-4222-8222-222222222222";
const CHANNEL = "9f1b4e8a-6f3c-4c2a-9a6d-2f7e5c1b3d40";

/**
 * Spec 030 (R14.1, 14.2, 14.9): the agents of one client. Each action with
 * the exact permission the API asks for — `agents:write` to create, rename
 * or archive; `channels:write` to give a number to an agent — and the API's
 * refusal comes back as its code for the screen to say in words.
 */
describe("los agentes de un cliente", () => {
  it("un editor crea, renombra y archiva; la ficha entera se vuelve a pintar", async () => {
    h.setRole("builder");
    expect(
      await createAgentAction({ ref: "demo", name: " Ventas ", seed_template: "generic_v1", placeholders: { "tenant.address": "Calle 1" } }),
    ).toMatchObject({ ok: true });
    expect(h.backend.createAgent).toHaveBeenCalledWith("demo", {
      name: "Ventas",
      seed_template: "generic_v1",
      placeholders: { "tenant.address": "Calle 1" },
    });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");

    expect(await renameAgentAction({ ref: "demo", agent: AGENT, name: "Ventas online" })).toMatchObject({ ok: true });
    expect(h.backend.updateAgent).toHaveBeenLastCalledWith("demo", AGENT, { name: "Ventas online" });
    expect(await archiveAgentAction({ ref: "demo", agent: AGENT })).toMatchObject({ ok: true });
    expect(h.backend.updateAgent).toHaveBeenLastCalledWith("demo", AGENT, { status: "archived" });
  });

  it("dar un número a un agente pide permiso de canales", async () => {
    h.setRole("builder");
    expect(await assignChannelAgentAction({ ref: "demo", channel: CHANNEL, agent: AGENT })).toMatchObject({ ok: true });
    expect(h.backend.assignChannelAgent).toHaveBeenCalledWith("demo", CHANNEL, AGENT);
  });

  it("la negativa de la API vuelve con su código", async () => {
    h.setRole("owner");
    h.fail("createAgent", 409, "", "name_taken");
    expect(await createAgentAction({ ref: "demo", name: "Ventas", seed_template: "generic_v1" })).toMatchObject({
      ok: false,
      status: 409,
      code: "name_taken",
    });
    h.fail("assignChannelAgent", 409, "", "agent_not_published");
    expect(await assignChannelAgentAction({ ref: "demo", channel: CHANNEL, agent: AGENT })).toMatchObject({
      ok: false,
      code: "agent_not_published",
    });
  });

  it("un analista no toca nada, y no se llega a llamar al backend", async () => {
    h.setRole("analyst");
    const calls = [h.backend.createAgent, h.backend.updateAgent, h.backend.assignChannelAgent];
    for (const fn of calls) fn.mockClear();
    expect(await createAgentAction({ ref: "demo", name: "x", seed_template: "generic_v1" })).toEqual(h.denied());
    expect(await renameAgentAction({ ref: "demo", agent: AGENT, name: "x" })).toEqual(h.denied());
    expect(await archiveAgentAction({ ref: "demo", agent: AGENT })).toEqual(h.denied());
    expect(await assignChannelAgentAction({ ref: "demo", channel: CHANNEL, agent: AGENT })).toEqual(h.denied());
    for (const fn of calls) expect(fn).not.toHaveBeenCalled();
  });

  it("lo que no es un id no llega a la URL", async () => {
    h.setRole("owner");
    await expect(archiveAgentAction({ ref: "demo", agent: "../otro" })).rejects.toThrow();
    await expect(renameAgentAction({ ref: "demo", agent: AGENT, name: "x".repeat(81) })).rejects.toThrow();
  });
});
