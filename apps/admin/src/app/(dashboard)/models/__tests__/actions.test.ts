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
