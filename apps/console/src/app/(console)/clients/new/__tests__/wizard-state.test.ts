import { describe, expect, it } from "vitest";

import { messages, t, type MessageKey } from "@/i18n/messages";
import type { SeedPlaceholder, SeedTemplate } from "@/lib/backend/onboarding";

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
  requiredPlaceholders,
  STEPS,
} from "../wizard-state";

describe("wizard-state", () => {
  it("plans stages from the choices", () => {
    // Spec 019: dos etapas, las que llaman al servidor. Publicar y activar se
    // retiraron con la pregunta que las elegía.
    expect(planStages({ seed_template: null }).map((s) => s.status)).toEqual(["pending", "skipped"]);
    const full = planStages({ seed_template: "generic_v1" });
    expect(full.map((s) => s.key)).toEqual(["create", "seed"]);
    expect(full.every((s) => s.status === "pending")).toBe(true);
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

  it("reintentar una etapa no toca la anterior (spec 016 R4.2, spec 019)", () => {
    // Lo que esto protege: el cliente ya existe. Reintentar no puede volver a
    // crearlo ni perder lo hecho.
    let st = planStages({ seed_template: "generic_v1" });
    st = stageReducer(st, { type: "start", key: "create", at: 1 });
    st = stageReducer(st, { type: "done", key: "create", at: 2 });
    st = stageReducer(st, { type: "start", key: "seed", at: 2 });
    st = stageReducer(st, { type: "fail", key: "seed", at: 3, error: "boom" });
    expect(runOutcome(st)).toBe("partial");
    expect(nextStage(st)).toBe("seed");
    const retried = stageReducer(st, { type: "reset", key: "seed" });
    expect(retried.find((s) => s.key === "create")?.status).toBe("done");
    expect(nextStage(retried)).toBe("seed");
  });
});

/**
 * Spec 019 · qué campos pide de verdad una plantilla.
 *
 * El alta dejó de enseñar los opcionales (owner, 2026-09-28: «los datos
 * básicos los rellenamos acá y los datos más avanzados en los ajustes del
 * agente»). Lo que queda es lo que el renderizador de semillas **exige** para
 * poder escribir el prompt, y eso no es una lista escrita a mano: sale de la
 * propia plantilla.
 *
 * Los números vienen de la Fase 0, ejecutando `render_seed_template` contra
 * las trece semillas con los campos vacíos (`specs/019-alta-deja-pesar/
 * research-probe.py`). Si una semilla cambia, este test lo cuenta.
 */
describe("requiredPlaceholders (spec 019)", () => {
  const ph = (key: string, required: boolean): SeedPlaceholder => ({
    key,
    required,
    secret: false,
    kind: "text",
    example: null,
  });
  const tpl = (placeholders: SeedPlaceholder[]): SeedTemplate => ({
    name: "x_v1",
    display_name: "X",
    version: "1",
    vertical: "x",
    tools_count: 3,
    placeholders,
  });

  it("solo los que la plantilla exige, en el orden en que llegan", () => {
    const t = tpl([
      ph("tenant.address", true),
      ph("agent.tone", false),
      ph("tenant.business_hours_label", true),
      ph("agent.name", false),
    ]);
    expect(requiredPlaceholders(t).map((p) => p.key)).toEqual([
      "tenant.address",
      "tenant.business_hours_label",
    ]);
  });

  it("una plantilla sin exigencias no pide nada", () => {
    // Tres de las trece: cobranza, inventario y woocommerce_sales.
    expect(requiredPlaceholders(tpl([ph("agent.name", false)]))).toEqual([]);
  });

  it("sin plantilla no hay campos que pedir", () => {
    expect(requiredPlaceholders(null)).toEqual([]);
  });

  it("**no** devuelve los opcionales, que es justo lo que el alta dejó de enseñar", () => {
    // Antes, la plantilla marcada por defecto enseñaba 23 campos y solo 12
    // hacían falta. Las once restantes tenían valor por defecto y se pedían
    // igual.
    const once = Array.from({ length: 11 }, (_, i) => ph(`policies.x${i}`, false));
    expect(requiredPlaceholders(tpl([ph("tenant.address", true), ...once]))).toHaveLength(1);
  });
});

/**
 * Spec 019 · tres pasos, y ninguno que no haga nada.
 *
 * El paso «Canal» se retiró (R3.1): su respuesta no viajaba al servidor ni
 * quedaba en el cliente — `case "channel": return done()`. Un cuarto del
 * asistente para una pregunta que se descartaba.
 *
 * Y publicar dejó de preguntarse (R6.4): un cliente no atiende hasta estar
 * configurado y con canal, así que elegirlo al crear no adelantaba nada.
 */
describe("los pasos del alta (spec 019)", () => {
  it("son tres, y la plantilla va primera", () => {
    // Primera porque decide el prompt, las herramientas y qué campos existen
    // siquiera: decidirla antes estrecha todo lo demás (R2.1).
    expect(STEPS).toEqual(["template", "details", "review"]);
  });

  it("no hay paso de canal", () => {
    expect(STEPS).not.toContain("channel");
  });
});

describe("las etapas del alta (spec 019)", () => {
  it("son crear y escribir el agente: las que de verdad llaman al servidor", () => {
    expect(planStages({ seed_template: "barbershop_v1" }).map((s) => s.key)).toEqual(["create", "seed"]);
  });

  it("sin plantilla no se escribe agente, y se dice que se salta", () => {
    const stages = planStages({ seed_template: null });
    expect(stages.find((s) => s.key === "seed")?.status).toBe("skipped");
    expect(stages.find((s) => s.key === "create")?.status).toBe("pending");
  });

  it("no hay etapa de publicar ni de activar", () => {
    // Se quedan como guardia: si vuelven, es con una decisión escrita.
    const keys = planStages({ seed_template: "barbershop_v1" }).map((s) => s.key);
    expect(keys).not.toContain("publish");
    expect(keys).not.toContain("activate");
    expect(keys).not.toContain("channel");
  });
});
