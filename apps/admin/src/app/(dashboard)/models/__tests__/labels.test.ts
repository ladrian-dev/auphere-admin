import { describe, expect, it } from "vitest";

import { DRIFT, POLICY, WHISPER, row } from "./fixtures";

import {
  STATUS_FILTERS,
  STATUS_LABEL,
  blockedLabel,
  checkWeights,
  formatAmount,
  formatMultiplier,
  formatPrice,
  laneMultiplier,
  multiplierBody,
  priceFormFrom,
  proposalFor,
  saleChip,
  todayUtc,
  isInUse,
  joinEs,
  refusalWords,
  useLabel,
  usesLines,
  newDeploymentBody,
  priceBody,
  proposalLabel,
  retireAfterIso,
  type NewDeploymentForm,
  type PriceForm,
} from "../labels";

const NEW: NewDeploymentForm = {
  id: "bedrock/eu.anthropic.claude-haiku-5-5",
  display_name: "Claude Haiku 5.5 · Bedrock UE",
  model: "claude-haiku-5-5",
  provider: "aws_bedrock",
  family: "anthropic-claude",
  route: "eu.anthropic.claude-haiku-5-5",
  region: "eu-south-2",
  residency: "eu",
  license_id: "",
  license_url: "",
  capabilities: '{"tools": true, "tier": "basic"}',
  reason: "Candidato de router-and-catalog §3",
};

const PRICE: PriceForm = {
  valid_from: "2026-11-01",
  input: "0,11",
  cache_read: "",
  cache_write: "",
  output: "0.55",
  audio_minute: "",
  source: "https://aws.amazon.com/bedrock/pricing/",
  currency: "USD",
};

/** Spec 047 (T150, historia 24): the catalog's words and rules. */
describe("catalog labels", () => {
  it("names every state in Spanish and filters by the ones an operator looks for", () => {
    expect(STATUS_LABEL.unavailable).toBe("No disponible");
    expect(STATUS_LABEL.retiring).toBe("En retirada");
    expect(STATUS_FILTERS.map((f) => f.key)).toEqual(["all", "active", "draft", "retiring", "unavailable"]);
  });

  it("formats a price per million tokens, and says when there is none", () => {
    expect(formatPrice(null)).toBe("Sin precio");
    const text = formatPrice({
      valid_from: "2026-10-01",
      source: null,
      currency: "USD",
      unit: "per_million_tokens",
      input: 0.11,
      cache_read: null,
      cache_write: null,
      output: 0.55,
    });
    expect(text).toContain("entrada");
    expect(text).toContain("salida");
    expect(text).not.toContain("caché");
  });

  it("proposes «Automático» when no substitute is certified", () => {
    const p = { tenant_id: "t", agent_id: "a", client_ref: "c-1", agent: "Reservas" };
    expect(proposalLabel({ ...p, proposed: "auto" })).toBe("«Automático»");
    expect(proposalLabel({ ...p, proposed: "prov/near" })).toBe("prov/near");
  });

  it("retires at 00:00 UTC of the chosen day", () => {
    expect(retireAfterIso("2026-12-01")).toBe("2026-12-01T00:00:00+00:00");
    expect(retireAfterIso("1/12/2026")).toBeNull();
  });
});

describe("a new deployment", () => {
  it("is a draft that claims no retention and no contract (research D44)", () => {
    const checked = newDeploymentBody(NEW);
    expect(checked.ok).toBe(true);
    if (!checked.ok) return;
    expect(checked.body.retention).toEqual({ zero: false, how: null });
    expect(checked.body.contract).toEqual({ dpa: false, subprocessor_listed: false });
    expect(checked.body.capabilities).toEqual({ tools: true, tier: "basic" });
    expect(checked.body.license).toBeNull();
  });

  it("says what is wrong next to each field", () => {
    const checked = newDeploymentBody({ ...NEW, id: "No Vale", reason: " ", capabilities: "[1]" });
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(Object.keys(checked.errors).sort()).toEqual(["capabilities", "id", "reason"]);
  });

  it("keeps the license with its link, unread", () => {
    const checked = newDeploymentBody({ ...NEW, license_id: "apache-2.0", license_url: "https://x/LICENSE" });
    expect(checked.ok && checked.body.license).toEqual({ id: "apache-2.0", url: "https://x/LICENSE", read_at: null });
  });
});

describe("a new price", () => {
  it("enters with its date and its source, in numbers", () => {
    const checked = priceBody(PRICE, "2026-11-01");
    expect(checked).toEqual({
      ok: true,
      body: {
        valid_from: "2026-11-01",
        input: 0.11,
        output: 0.55,
        source: "https://aws.amazon.com/bedrock/pricing/",
        currency: "USD",
      },
    });
  });

  it("refuses a price without source, without date or without any tariff", () => {
    const checked = priceBody({ ...PRICE, valid_from: "", source: "", input: "", output: "-1" }, "2026-11-01");
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(Object.keys(checked.errors).sort()).toEqual(["input", "output", "source", "valid_from"]);
  });
});

/** Spec 059, historia 1: what uses a model, and why the API refused, in words. */
describe("the uses of a model", () => {
  const free = { defaults: [], agents: 0, clients: [], verified: true, problem: null };

  it("is in use by a default, by an agent or by a client's assignment", () => {
    expect(isInUse(free)).toBe(false);
    expect(isInUse({ ...free, defaults: ["judge"] })).toBe(true);
    expect(isInUse({ ...free, agents: 1, clients: ["Spa Jemma"] })).toBe(true);
    expect(isInUse({ ...free, clients: ["Spa Jemma"] })).toBe(true);
  });

  it("names each default, and keeps the code of one it does not know", () => {
    expect(useLabel("respond")).toBe("responder");
    expect(useLabel("respond_fallback")).toBe("reserva de responder");
    expect(useLabel("booking_brake")).toBe("freno de reservas");
    expect(useLabel("new_task_2027")).toBe("new_task_2027");
  });

  it("joins a list the Spanish way", () => {
    expect(joinEs([])).toBe("");
    expect(joinEs(["a"])).toBe("a");
    expect(joinEs(["a", "b"])).toBe("a y b");
    expect(joinEs(["a", "b", "c"])).toBe("a, b y c");
  });

  it("says the defaults and the agents apart", () => {
    expect(usesLines(free)).toEqual({ defaults: null, agents: null });
    expect(
      usesLines({ ...free, defaults: ["respond", "respond_fallback"], agents: 7, clients: ["Amigable Cobro", "New Air"] }),
    ).toEqual({
      defaults: "Por defecto para responder y reserva de responder",
      agents: "7 agentes de Amigable Cobro y New Air",
    });
    expect(usesLines({ ...free, agents: 1, clients: ["Spa Jemma"] }).agents).toBe("1 agente de Spa Jemma");
    expect(usesLines({ ...free, clients: ["Spa Jemma"] }).agents).toBe("Asignado por Spa Jemma");
  });

  it("paints a stopped retirement only with agents inside", () => {
    expect(blockedLabel(null)).toBeNull();
    expect(blockedLabel(0)).toBeNull();
    expect(blockedLabel(1)).toBe("Retirada detenida (1 agente)");
    expect(blockedLabel(4)).toBe("Retirada detenida (4 agentes)");
  });
});

describe("a refusal of the API, in words", () => {
  it("names every use of a model in use, and says nothing changed", () => {
    const text = refusalWords({
      code: "model_in_use",
      defaults: ["respond", "respond_fallback"],
      agents: 7,
      clients: ["Amigable Cobro", "New Air"],
    });
    expect(text).toContain("por defecto para responder y reserva de responder");
    expect(text).toContain("7 agentes de Amigable Cobro y New Air");
    expect(text).toContain("no cambia de estado");
  });

  it("names the clients of a model only assigned, without agents", () => {
    const text = refusalWords({ code: "model_in_use", defaults: [], agents: 0, clients: ["Spa Jemma"] });
    expect(text).toBe("El modelo está en uso: lo tiene asignado Spa Jemma. Por eso no cambia de estado.");
  });

  it("says why the worker's models could not be checked", () => {
    for (const problem of ["no_heartbeat", "unpublished", "mismatch"]) {
      const text = refusalWords({ code: "defaults_unverified", problem });
      expect(text).toContain("No se puede comprobar");
      expect(text).toContain("no cambia de estado");
    }
    expect(refusalWords({ code: "defaults_unverified", problem: "no_heartbeat" })).toContain("ningún worker");
  });

  it("names the lanes under the floor", () => {
    expect(refusalWords({ code: "below_floor", lanes: ["output"] })).toContain("salida");
    expect(refusalWords({ code: "below_floor", lanes: ["input", "cache_read"] })).toContain("entrada y caché");
  });

  it("leaves the rest to the table of errors", () => {
    expect(refusalWords({ code: "reason_required" })).toBeNull();
    expect(refusalWords({ code: "below_floor" })).toBeNull();
  });
});

/** Spec 059, historias 3 y 4: the sale, the cost and their rules. */
describe("numbers of the catalog", () => {
  it("writes amounts and multipliers the Spanish way", () => {
    expect(formatAmount("4.000000")).toBe("4,00");
    expect(formatAmount("0.088000")).toBe("0,088");
    expect(formatAmount(20)).toBe("20,00");
    expect(formatAmount(null)).toBe("—");
    expect(formatMultiplier("2.20")).toBe("2,2×");
    expect(formatMultiplier("1.76")).toBe("1,76×");
    expect(formatMultiplier(null)).toBe("—");
  });

  it("judges «hoy» by the UTC day, as the API does", () => {
    expect(todayUtc(new Date("2026-11-11T23:30:00-05:00"))).toBe("2026-11-12");
  });

  it("computes the multiplier of a lane: weight × 10 ÷ cost", () => {
    expect(laneMultiplier("20", "4.4", "10")).toBeCloseTo(2.2);
    expect(laneMultiplier("25", "4.4", "10")).toBeCloseTo(1.76);
    expect(laneMultiplier(null, "4.4", "10")).toBeNull();
    expect(laneMultiplier("0", "4.4", "10")).toBeNull();
  });

  it("proposes the weights of the target multiplier over the cost, to six decimals", () => {
    expect(proposalFor({ input: 4, cache_read: 0.4, output: 25 }, "2.2", "10")).toEqual({
      input: "0.88",
      cache_read: "0.088",
      output: "5.5",
    });
    expect(proposalFor({ input: 0.15, cache_read: 0.075, output: 0.6 }, "2.2", "10")).toEqual({
      input: "0.033",
      cache_read: "0.0165",
      output: "0.132",
    });
    expect(proposalFor({ input: 4, cache_read: null, output: 25 }, "2.2", "10")).toBeNull();
    expect(proposalFor({ input: 4, cache_read: 0.4, output: 25 }, null, "10")).toBeNull();
  });
});

describe("the chip of the sale (3.8, 3.11)", () => {
  it("names each state", () => {
    expect(saleChip(row().sale, true)).toEqual({ label: "En el objetivo", tone: "positive" });
    expect(saleChip(DRIFT.sale, true)).toEqual({ label: "Desfasado", tone: "warning" });
    expect(saleChip({ ...DRIFT.sale, state: "below_floor" }, true)).toEqual({ label: "Bajo el suelo", tone: "danger" });
    expect(saleChip({ ...DRIFT.sale, state: "unweighted" }, true)).toEqual({ label: "Sin pesos", tone: "warning" });
    expect(saleChip(WHISPER.sale, true)).toEqual({ label: "Por minuto", tone: "muted" });
  });

  it("without the target multiplier, does not judge on target or drift", () => {
    expect(saleChip(row().sale, false)).toBeNull();
    expect(saleChip(DRIFT.sale, false)).toBeNull();
    expect(saleChip({ ...DRIFT.sale, state: "below_floor" }, false)).toEqual({ label: "Bajo el suelo", tone: "danger" });
  });
});

describe("the cost (4.3, 4.4)", () => {
  it("starts from the cost in force and today", () => {
    const form = priceFormFrom(row(), "2026-11-11");
    expect(form).toMatchObject({
      valid_from: "2026-11-11",
      input: "4",
      cache_read: "0,4",
      output: "20",
      cache_write: "",
      source: "https://openai.com/api/pricing/",
      currency: "USD",
    });
  });

  it("refuses a date before today, with its reason", () => {
    const checked = priceBody(priceFormFrom(row(), "2026-11-10"), "2026-11-11");
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(checked.errors.valid_from).toMatch(/antes de hoy/);
    expect(priceBody(priceFormFrom(row(), "2026-11-12"), "2026-11-11").ok).toBe(true);
  });
});

describe("the weights (3.4, 3.5)", () => {
  const costs = { input: "4", cache_read: "0.4", output: "25" };
  const form = { input: "0,88", cache_read: "0,088", output: "5,5", reason: "Subió la salida" };

  it("go as decimals with a dot, with their reason", () => {
    expect(checkWeights(form, costs, POLICY)).toEqual({
      ok: true,
      body: { input: "0.88", cache_read: "0.088", output: "5.5", reason: "Subió la salida" },
    });
  });

  it("are the three or none", () => {
    const checked = checkWeights({ ...form, cache_read: "" }, costs, POLICY);
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(checked.errors.cache_read).toBeTruthy();
  });

  it("refuse a lane under 1,5 times its cost, naming it, and exactly on the floor is fine", () => {
    const low = checkWeights({ ...form, output: "3.7" }, costs, POLICY);
    expect(low.ok).toBe(false);
    if (low.ok) return;
    expect(Object.keys(low.errors)).toEqual(["output"]);
    expect(low.errors.output).toMatch(/suelo/);
    expect(checkWeights({ ...form, output: "3.75" }, costs, POLICY).ok).toBe(true);
    expect(checkWeights({ ...form, cache_read: "0.06" }, costs, POLICY).ok).toBe(true);
  });

  it("need a reason and positive numbers", () => {
    const checked = checkWeights({ ...form, input: "0", reason: " " }, costs, POLICY);
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(Object.keys(checked.errors).sort()).toEqual(["input", "reason"]);
  });

  it("without a cost, there is no floor to check", () => {
    expect(checkWeights({ ...form, output: "0.1" }, {}, POLICY).ok).toBe(true);
  });
});

describe("the target multiplier (3.6, 3.7)", () => {
  it("goes with its reason and the choice of applying it to all", () => {
    expect(multiplierBody({ multiplier: "2,5", apply_to_all: true, reason: "Margen" })).toEqual({
      ok: true,
      body: { multiplier: "2.5", apply_to_all: true, reason: "Margen" },
    });
  });

  it("refuses less than the floor, and no reason", () => {
    const checked = multiplierBody({ multiplier: "1.4", apply_to_all: false, reason: "" });
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(checked.errors.multiplier).toMatch(/1,5/);
    expect(checked.errors.reason).toBeTruthy();
    expect(multiplierBody({ multiplier: "1.5", apply_to_all: false, reason: "x" }).ok).toBe(true);
  });
});
