import { beforeEach, describe, expect, it, vi } from "vitest";

const h = await vi.hoisted(async () => (await import("@/test/actions")).actionHarness());
vi.mock("@/lib/principal", () => h.principalModule);
vi.mock("@/lib/backend", () => h.backendModule);
vi.mock("next/cache", () => h.cacheModule);

const { agendaToolsAction, agentAgendaAction, setAgentAgendaAction } = await import("../agenda-actions");

const AGENT = "11111111-1111-4111-8111-111111111111";
const ids = { ref: "demo", agent: AGENT };

/**
 * Spec 057 (T029; requisitos 2.1–2.5, 7.1–7.3; `contracts/console-api.md` §3–§5)
 * — la agenda de un agente: `agents:read` para leerla y ver lo que puede hacer,
 * `agents:write` para activarla o desactivarla. El cliente y el agente salen de
 * la ruta: un cuerpo con `tenant_id` o `partner_id` no pasa de la acción, y el
 * analista recibe el «no puedes» de la consola sin llamar a la API.
 */
describe("la agenda de un agente · leer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("permitido: lee la agenda del agente de la ruta, también un analista, y no refresca nada", async () => {
    h.setRole("analyst");
    h.backend.getAgentAgenda.mockResolvedValueOnce({ offered: true });
    expect(await agentAgendaAction(ids)).toMatchObject({ ok: true, data: { offered: true } });
    expect(h.backend.getAgentAgenda).toHaveBeenCalledWith("demo", AGENT);
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
  });

  it("denegado: un agente que no es un uuid o un campo de más no llegan a la API", async () => {
    await expect(agentAgendaAction({ ref: "demo", agent: "otro" })).rejects.toThrow();
    await expect(agentAgendaAction({ ...ids, tenant_id: "t-2" })).rejects.toThrow();
    h.setClient(["reservas"]);
    expect(await agentAgendaAction(ids)).toEqual(h.denied());
    expect(h.backend.getAgentAgenda).not.toHaveBeenCalled();
  });
});

describe("la agenda de un agente · activar y desactivar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("permitido: activar con el modo de Reservas, desactivar sin él, y refresca el cliente", async () => {
    await setAgentAgendaAction({ ...ids, enabled: true, reservas: { mode: "capacity", capacity_kind: "restaurant" } });
    expect(h.backend.setAgentAgenda).toHaveBeenLastCalledWith("demo", AGENT, {
      enabled: true,
      reservas: { mode: "capacity", capacity_kind: "restaurant" },
    });
    await setAgentAgendaAction({ ...ids, enabled: false });
    expect(h.backend.setAgentAgenda).toHaveBeenLastCalledWith("demo", AGENT, { enabled: false });
    expect(h.cacheModule.revalidatePath).toHaveBeenCalledWith("/clients/demo", "layout");
  });

  it("los códigos de la API vuelven tal cual, con el máximo", async () => {
    h.fail("setAgentAgenda", 422, "", "too_many_tools", { max: 60 });
    expect(await setAgentAgendaAction({ ...ids, enabled: true })).toMatchObject({ ok: false, status: 422, code: "too_many_tools", info: { max: 60 } });
    expect(h.cacheModule.revalidatePath).not.toHaveBeenCalled();
  });

  it("denegado: el analista no la cambia, y un `tenant_id` o un `partner_id` no pasan", async () => {
    h.setRole("analyst");
    expect(await setAgentAgendaAction({ ...ids, enabled: true })).toEqual(h.denied());
    h.setRole("builder");
    await expect(setAgentAgendaAction({ ...ids, enabled: true, tenant_id: "t-2" })).rejects.toThrow();
    await expect(setAgentAgendaAction({ ...ids, enabled: true, reservas: { mode: "services", partner_id: "p-2" } })).rejects.toThrow();
    expect(h.backend.setAgentAgenda).not.toHaveBeenCalled();
  });
});

describe("la agenda de un agente · qué puede hacer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.setRole("builder");
  });

  it("permitido: lee las 9 en el idioma de la consola", async () => {
    h.setRole("analyst");
    await agendaToolsAction({ ...ids, lang: "en" });
    expect(h.backend.agendaTools).toHaveBeenCalledWith("demo", AGENT, "en");
  });

  it("denegado: un idioma que no existe no pasa, y una persona del cliente no lee", async () => {
    await expect(agendaToolsAction({ ...ids, lang: "fr" })).rejects.toThrow();
    h.setClient(["reservas"]);
    expect(await agendaToolsAction({ ...ids, lang: "es" })).toEqual(h.denied());
    expect(h.backend.agendaTools).not.toHaveBeenCalled();
  });
});
