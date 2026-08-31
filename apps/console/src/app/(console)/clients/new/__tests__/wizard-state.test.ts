import { describe, expect, it } from "vitest";

import { messages, t, type MessageKey } from "@/i18n/messages";

import {
  SEED_PLACEHOLDER_KEYS,
  cleanPlaceholders,
  decideWizardRefCheck,
  elapsedSeconds,
  missingPlaceholders,
  nextStage,
  planStages,
  resolvePlaceholderLabel,
  runOutcome,
  slugify,
  stageReducer,
  wizardIsDirty,
  wizardShouldBlockLeave,
  WIZARD_TIMEZONE_INITIAL,
  isIanaTimeZone,
  pickWizardTimezone,
  wizardTimezoneOptions,
} from "../wizard-state";

describe("wizard-state", () => {
  it("plans stages from the choices", () => {
    expect(planStages({ seed_template: null, publish_now: true }).map((s) => s.status)).toEqual([
      "pending",
      "skipped",
      "skipped",
      "pending",
    ]);
    expect(planStages({ seed_template: "generic_v1", publish_now: false }).map((s) => s.status)).toEqual([
      "pending",
      "pending",
      "skipped",
      "pending",
    ]);
    expect(planStages({ seed_template: "generic_v1", publish_now: true }).every((s) => s.status === "pending")).toBe(true);
  });

  it("reduces stage events and reports the outcome", () => {
    let st = planStages({ seed_template: "generic_v1", publish_now: false });
    expect(runOutcome(st)).toBe("idle");
    expect(nextStage(st)).toBe("create");
    st = stageReducer(st, { type: "start", key: "create", at: 1000 });
    expect(runOutcome(st)).toBe("running");
    st = stageReducer(st, { type: "done", key: "create", at: 1500 });
    st = stageReducer(st, { type: "start", key: "seed", at: 1500 });
    st = stageReducer(st, { type: "fail", key: "seed", at: 2200, error: "missing placeholder" });
    expect(runOutcome(st)).toBe("partial");
    expect(nextStage(st)).toBe("seed");
    expect(st[1]!.error).toBe("missing placeholder");
    st = stageReducer(st, { type: "start", key: "seed", at: 3000 });
    st = stageReducer(st, { type: "done", key: "seed", at: 3400 });
    st = stageReducer(st, { type: "start", key: "channel", at: 3400 });
    st = stageReducer(st, { type: "done", key: "channel", at: 3400 });
    expect(runOutcome(st)).toBe("done");
    expect(nextStage(st)).toBeNull();
    expect(elapsedSeconds(st)).toBe(2.4);
  });

  it("validates placeholders", () => {
    const defs = [
      { key: "tenant.address", required: true, secret: false, kind: "text" as const, example: null },
      { key: "agent.name", required: false, secret: false, kind: "text" as const, example: "Alex" },
    ];
    expect(missingPlaceholders(defs, {})).toEqual(["tenant.address"]);
    expect(missingPlaceholders(defs, { "tenant.address": "  " })).toEqual(["tenant.address"]);
    expect(missingPlaceholders(defs, { "tenant.address": "x" })).toEqual([]);
    expect(cleanPlaceholders({ a: " x ", b: "", c: "  " })).toEqual({ a: "x" });
  });

  it("slugifies names into refs", () => {
    expect(slugify("Clínica Boreal — Caracas")).toBe("clinica-boreal-caracas");
  });
});

describe("wizardIsDirty (QA-04)", () => {
  const clean = { name: "", external_client_ref: "", placeholders: {} };
  it("empty defaults are clean", () => {
    expect(wizardIsDirty(clean)).toBe(false);
    expect(wizardIsDirty({ ...clean, placeholders: { "tenant.address": "  " } })).toBe(false);
  });
  it("any filled field is dirty", () => {
    expect(wizardIsDirty({ ...clean, name: "Demo" })).toBe(true);
    expect(wizardIsDirty({ ...clean, external_client_ref: "demo" })).toBe(true);
    expect(wizardIsDirty({ ...clean, placeholders: { "tenant.address": "x" } })).toBe(true);
  });
});

describe("decideWizardRefCheck (QA-02)", () => {
  const msg = "A client with this reference already exists.";
  it("existing ref → 409 stay on details", () => {
    expect(decideWizardRefCheck({ found: true }, msg)).toEqual({
      allowNext: false,
      result: { ok: false, status: 409, message: msg },
    });
  });
  it("missing ref (404) → allow next", () => {
    expect(decideWizardRefCheck({ found: false, status: 404, message: "Unknown client reference" }, msg)).toEqual({
      allowNext: true,
    });
  });
});

describe("resolvePlaceholderLabel (QA-03)", () => {
  it("every known seed placeholder key resolves and never returns the raw key", () => {
    for (const key of SEED_PLACEHOLDER_KEYS) {
      const ph = `ph.${key}`;
      expect(ph in messages, ph).toBe(true);
      const es = resolvePlaceholderLabel(key, messages, (k) => t("es", k as MessageKey));
      const en = resolvePlaceholderLabel(key, messages, (k) => t("en", k as MessageKey));
      expect(es).not.toBe(key);
      expect(en).not.toBe(key);
      expect(es).not.toBe(ph);
      expect(en).not.toBe(ph);
    }
  });
});


describe("wizardShouldBlockLeave (QA-04)", () => {
  it("blocks only when dirty and not done", () => {
    expect(wizardShouldBlockLeave(true, "idle")).toBe(true);
    expect(wizardShouldBlockLeave(true, "running")).toBe(true);
    expect(wizardShouldBlockLeave(true, "partial")).toBe(true);
    expect(wizardShouldBlockLeave(true, "done")).toBe(false);
    expect(wizardShouldBlockLeave(false, "idle")).toBe(false);
  });
});

describe("wizard timezone (QA-06)", () => {
  it("starts empty — no Europe/Madrid default", () => {
    expect(WIZARD_TIMEZONE_INITIAL).toBe("");
  });
  it("select options are IANA and include the browser zone", () => {
    const opts = wizardTimezoneOptions("Pacific/Honolulu");
    expect(opts).toContain("Pacific/Honolulu");
    expect(opts).not.toContain("Caracas Venezuela");
    expect(pickWizardTimezone("Pacific/Honolulu", opts)).toBe("Pacific/Honolulu");
    expect(pickWizardTimezone("Not/AZone", opts)).toBe("");
  });
  it("accepts real IANA and rejects labels", () => {
    expect(isIanaTimeZone("America/Los_Angeles")).toBe(true);
    expect(isIanaTimeZone("")).toBe(false);
    expect(isIanaTimeZone("Caracas Venezuela")).toBe(false);
  });
});
