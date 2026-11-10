import { describe, expect, it } from "vitest";

import {
  STATUS_FILTERS,
  STATUS_LABEL,
  formatPrice,
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
    const checked = priceBody(PRICE);
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
    const checked = priceBody({ ...PRICE, valid_from: "", source: "", input: "", output: "-1" });
    expect(checked.ok).toBe(false);
    if (checked.ok) return;
    expect(Object.keys(checked.errors).sort()).toEqual(["input", "output", "source", "valid_from"]);
  });
});
