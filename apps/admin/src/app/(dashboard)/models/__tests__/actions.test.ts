/**
 * Spec 059 (`contracts/admin-api.md` §1–§7): the panel's calls to the catalog
 * and how its actions word a refusal, with the API simulated by `fetch`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/session", () => ({ requireOperator: async () => ({ id: "op-1" }) }));

const { modelsBackend } = await import("@/lib/backend-models");
const actions = await import("../actions");

type Sent = { url: string; method: string; headers: Record<string, string>; body: unknown };

const sent: Sent[] = [];
let reply: { status: number; body: unknown } = { status: 200, body: {} };

beforeEach(() => {
  sent.length = 0;
  reply = { status: 200, body: {} };
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    sent.push({
      url,
      method: init.method ?? "GET",
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
    });
    const text = reply.body === undefined ? "" : JSON.stringify(reply.body);
    return new Response(text, { status: reply.status, headers: { "Content-Type": "application/json" } });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const last = () => sent[sent.length - 1]!;

describe("the new calls of the catalog", () => {
  it("cancels a retirement and restores a model, each with the operator and its reason (§4, §5)", async () => {
    await modelsBackend.cancelRetirement("d1", "Nos equivocamos", "op-1");
    expect(last().method).toBe("POST");
    expect(last().url).toMatch(/\/admin\/models\/deployments\/d1\/cancel-retirement$/);
    expect(last().body).toEqual({ reason: "Nos equivocamos" });
    expect(last().headers["X-Operator-Id"]).toBe("op-1");

    await modelsBackend.restore("d1", "DPA firmado", "op-1");
    expect(last().url).toMatch(/\/admin\/models\/deployments\/d1\/restore$/);
    expect(last().body).toEqual({ reason: "DPA firmado" });
  });

  it("puts the three weights as decimals (§6)", async () => {
    await modelsBackend.putWeights("d1", { input: "0.88", cache_read: "0.088", output: "4.4", reason: "Subió el coste" }, "op-1");
    expect(last().method).toBe("PUT");
    expect(last().url).toMatch(/\/admin\/models\/deployments\/d1\/weights$/);
    expect(last().body).toEqual({ input: "0.88", cache_read: "0.088", output: "4.4", reason: "Subió el coste" });
    expect(last().headers["X-Operator-Id"]).toBe("op-1");
  });

  it("reads and changes the sale policy (§7)", async () => {
    reply = { status: 200, body: { multiplier: "2.2", floor: "1.5", sell_usd_per_million: "10" } };
    expect(await modelsBackend.getSalePolicy()).toEqual({ multiplier: "2.2", floor: "1.5", sell_usd_per_million: "10" });
    expect(last().url).toMatch(/\/admin\/models\/sale-policy$/);

    await modelsBackend.putSalePolicy({ multiplier: "2.5", apply_to_all: true, reason: "Margen" }, "op-1");
    expect(last().method).toBe("PUT");
    expect(last().body).toEqual({ multiplier: "2.5", apply_to_all: true, reason: "Margen" });
  });
});

describe("a refusal, in words", () => {
  it("«No disponible» on a model in use names its uses (§2)", async () => {
    reply = {
      status: 409,
      body: { detail: { code: "model_in_use", defaults: ["respond", "respond_fallback"], agents: 7, clients: ["Amigable Cobro"] } },
    };
    const result = await actions.unavailableAction("d1", "Rompió el DPA");
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.code).toBe("model_in_use");
    expect(result.error).toContain("responder");
    expect(result.error).toContain("7 agentes de Amigable Cobro");
  });

  it("«Retirar» without the worker's models says why (§2)", async () => {
    reply = { status: 409, body: { detail: { code: "defaults_unverified", problem: "unpublished" } } };
    const result = await actions.retireAction("d1", { retire_after: "2026-12-01T00:00:00+00:00", reason: "x" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain("No se puede comprobar");
  });

  it("a cost in the past is about the cost, not the retirement (§3)", async () => {
    reply = { status: 422, body: { detail: { code: "in_the_past" } } };
    const result = await actions.addPriceAction("d1", { valid_from: "2026-11-01", input: 4, source: "https://x.test/p", currency: "USD" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toMatch(/antes de hoy/);
    expect(result.error).not.toMatch(/retirada/);
  });

  it("weights under the floor name the lane (§6)", async () => {
    reply = { status: 422, body: { detail: { code: "below_floor", lanes: ["output"] } } };
    const result = await actions.putWeightsAction("d1", { input: "0.88", cache_read: "0.088", output: "1", reason: "x" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain("salida");
  });

  it("a multiplier under the floor says the floor (§7)", async () => {
    reply = { status: 422, body: { detail: { code: "below_floor" } } };
    const result = await actions.putSalePolicyAction({ multiplier: "1.2", apply_to_all: false, reason: "x" });
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain("1,5");
  });

  it("cancelling what is not in retirement, or restoring what is available", async () => {
    reply = { status: 409, body: { detail: { code: "not_retiring" } } };
    const cancel = await actions.cancelRetirementAction("d1", "x");
    expect(!cancel.ok && cancel.error).toContain("ya no está en retirada");
    reply = { status: 409, body: { detail: { code: "not_unavailable" } } };
    const restore = await actions.restoreAction("d1", "x");
    expect(!restore.ok && restore.error).toContain("ya no está «No disponible»");
  });
});

/**
 * Spec 065 (`specs/065-modelo-por-agente/contracts/api.md` § Panel de operador):
 * habilitar y deshabilitar un modelo para responder, el modelo por defecto de los
 * agentes y el modelo de cada agente. Cada escritura lleva al operador y su motivo.
 */
describe("spec 065: responder, el modelo por defecto y el de cada agente", () => {
  it("habilita con la nota de la pasada y deshabilita con el motivo", async () => {
    await modelsBackend.respondEnable("d1", "2026-11-24 · a1b2c3d · cable 42/42 · real 18/18", "op-1");
    expect(last().method).toBe("POST");
    expect(last().url).toMatch(/\/admin\/models\/deployments\/d1\/respond-enable$/);
    expect(last().body).toEqual({ note: "2026-11-24 · a1b2c3d · cable 42/42 · real 18/18" });
    expect(last().headers["X-Operator-Id"]).toBe("op-1");

    await modelsBackend.respondDisable("d1", "Falla la batería real", "op-1");
    expect(last().url).toMatch(/\/admin\/models\/deployments\/d1\/respond-disable$/);
    expect(last().body).toEqual({ reason: "Falla la batería real" });
    expect(last().headers["X-Operator-Id"]).toBe("op-1");
  });

  it("dice en palabras por qué no se habilita ni se deshabilita (409)", async () => {
    reply = { status: 409, body: { detail: { code: "no_respond_profile" } } };
    const enable = await actions.respondEnableAction("d1", "pasada");
    expect(!enable.ok && enable.error).toMatch(/perfil de llamada/);
    reply = { status: 422, body: { detail: { code: "not_active" } } };
    const inactive = await actions.respondEnableAction("d1", "pasada");
    expect(!inactive.ok && inactive.error).toBe("Solo se puede habilitar para responder un modelo activo.");

    // La de «Deshabilitar» dice sus usos en `uses`, no en `defaults` como la de «Retirar».
    reply = { status: 409, body: { detail: { code: "model_in_use", uses: ["agent_default", "respond_fallback_anthropic"] } } };
    const disable = await actions.respondDisableAction("d1", "x");
    expect(disable.ok).toBe(false);
    if (disable.ok) return;
    expect(disable.error).toBe(
      "El modelo está en uso: por defecto para los agentes sin modelo elegido y reserva de los modelos de Anthropic. Por eso no cambia de estado.",
    );
  });

  it("lee el modelo por defecto y lo cambia en dos pasos: primero la lista de afectados, después con confirmación", async () => {
    reply = { status: 200, body: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", set_by: null, set_at: null, options: [] } };
    expect(await modelsBackend.getRespondDefault()).toMatchObject({ model_id: "openai/gpt-5.6-sol" });
    expect(last().url).toMatch(/\/admin\/platform\/agent-respond-default$/);

    const affected = [
      { tenant_id: "t1", external_client_ref: "jemma", agent_id: "a1", agent_name: "Recepción", current_model: "openai/gpt-5.6-sol" },
    ];
    reply = { status: 409, body: { detail: { code: "confirm_required", affected } } };
    const preview = await actions.previewRespondDefaultAction("anthropic/claude-haiku-5-5");
    expect(last().method).toBe("PUT");
    expect(last().headers["X-Operator-Id"]).toBe("op-1");
    // Sin confirmar no se guarda nada, pero la API pide un motivo igual.
    expect(last().body).toMatchObject({ model_id: "anthropic/claude-haiku-5-5", confirm: false });
    expect(String((last().body as { reason: string }).reason).trim()).not.toBe("");
    expect(preview).toEqual({ ok: true, data: { affected } });

    reply = { status: 200, body: { model_id: "anthropic/claude-haiku-5-5", display_name: "Claude Haiku 5.5", set_by: "operator:luis@auphere.com", set_at: "2026-11-24T10:00:00Z", options: [] } };
    const saved = await actions.confirmRespondDefaultAction("anthropic/claude-haiku-5-5", "Haiku pasó la batería");
    expect(last().body).toEqual({ model_id: "anthropic/claude-haiku-5-5", reason: "Haiku pasó la batería", confirm: true });
    expect(saved.ok).toBe(true);

    reply = { status: 422, body: { detail: { code: "unknown_model", model_id: "x" } } };
    const refused = await actions.previewRespondDefaultAction("x");
    expect(!refused.ok && refused.error).toMatch(/no está habilitado para responder/);
  });

  it("lee el modelo de cada agente y lo cambia con el motivo", async () => {
    reply = { status: 200, body: [] };
    await modelsBackend.listAgentModels("t1");
    expect(last().url).toMatch(/\/admin\/tenants\/t1\/agents\/models$/);

    reply = { status: 200, body: {} };
    await modelsBackend.setAgentModel("t1", "a1", { model_id: null, reason: "Vuelve al de Auphere" }, "op-1");
    expect(last().method).toBe("PUT");
    expect(last().url).toMatch(/\/admin\/tenants\/t1\/agents\/a1\/model$/);
    expect(last().body).toEqual({ model_id: null, reason: "Vuelve al de Auphere" });
    expect(last().headers["X-Operator-Id"]).toBe("op-1");
  });
});
