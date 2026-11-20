/**
 * Spec 065 (T075; requisito 7.2): la acción del panel que cambia el modelo de un
 * agente, con la API simulada por `fetch`: lleva al operador y el motivo, vuelve
 * a pintar la pestaña y dice cada rechazo en palabras.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const cache = vi.hoisted(() => ({ revalidatePath: vi.fn() }));
vi.mock("next/cache", () => cache);
vi.mock("@/lib/session", () => ({ requireOperator: async () => ({ id: "op-1" }) }));

const { setAgentModelAction } = await import("../agent-model-actions");

const TENANT = "22222222-2222-4222-8222-222222222222";
const AGENT = "11111111-1111-4111-8111-000000000001";

type Sent = { url: string; method: string; headers: Record<string, string>; body: unknown };
const sent: Sent[] = [];
let reply: { status: number; body: unknown } = { status: 200, body: {} };

beforeEach(() => {
  sent.length = 0;
  cache.revalidatePath.mockReset();
  reply = { status: 200, body: {} };
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    sent.push({
      url,
      method: init.method ?? "GET",
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
    });
    return new Response(JSON.stringify(reply.body), { status: reply.status, headers: { "Content-Type": "application/json" } });
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("cambiar el modelo de un agente desde el panel", () => {
  it("manda el modelo y el motivo con el operador, y vuelve a pintar la pestaña", async () => {
    reply = { status: 200, body: { agent_id: AGENT, choice: null, effective: { model_id: "m", display_name: "M", source: "agent_operator" } } };
    const result = await setAgentModelAction(TENANT, AGENT, "anthropic/claude-haiku-5-5", "  Prueba  ");
    expect(result.ok).toBe(true);
    expect(sent[0]!.method).toBe("PUT");
    expect(sent[0]!.url).toMatch(new RegExp(`/admin/tenants/${TENANT}/agents/${AGENT}/model$`));
    expect(sent[0]!.body).toEqual({ model_id: "anthropic/claude-haiku-5-5", reason: "Prueba" });
    expect(sent[0]!.headers["X-Operator-Id"]).toBe("op-1");
    expect(cache.revalidatePath).toHaveBeenCalledWith(`/tenants/${TENANT}/agent`);
  });

  it("sin motivo no llama a la API", async () => {
    const result = await setAgentModelAction(TENANT, AGENT, null, "   ");
    expect(result).toMatchObject({ ok: false, error: "Hace falta el motivo." });
    expect(sent).toHaveLength(0);
  });

  it("un id que no es un UUID no llega a la URL", async () => {
    const result = await setAgentModelAction(TENANT, "../../x", null, "x");
    expect(result.ok).toBe(false);
    expect(sent).toHaveLength(0);
  });

  it("dice cada rechazo en palabras", async () => {
    reply = { status: 422, body: { detail: { code: "unknown_model", model_id: "x" } } };
    const unknown = await setAgentModelAction(TENANT, AGENT, "x", "r");
    expect(!unknown.ok && unknown.error).toBe(
      "No se pudo cambiar el modelo: ese modelo ya no está habilitado para responder. Recarga la página y elige otro.",
    );
    reply = { status: 422, body: { detail: { code: "model_unavailable_for_agent" } } };
    const cannot = await setAgentModelAction(TENANT, AGENT, "x", "r");
    expect(!cannot.ok && cannot.error).toMatch(/no puede ejecutar lo que usa este agente/);
    reply = { status: 404, body: { detail: "Agent not found" } };
    const gone = await setAgentModelAction(TENANT, AGENT, "x", "r");
    expect(!gone.ok && gone.error).toMatch(/ya no está activo/);
  });
});
