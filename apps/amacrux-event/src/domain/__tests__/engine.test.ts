import { describe, expect, it } from "vitest";

import { generateResult } from "../engine";
import { validateResult } from "../../lib/recommendation-provider";
import { frictionLabel } from "../copy";
import { PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_D, PROFILE_MANY } from "./fixtures";

const NOW = new Date("2026-09-16T10:00:00.000Z");
const CAPACITY = { sin_equipo: 2, limitado: 3, interno: 4, especializado: 5 } as const;

describe("motor de recomendaciones", () => {
  it("siempre devuelve exactamente tres recomendaciones con todos sus atributos", () => {
    for (const a of [PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_D, PROFILE_MANY]) {
      const r = generateResult(a, NOW);
      expect(r.recommendations).toHaveLength(3);
      for (const rec of r.recommendations) {
        expect(rec.reasons.length).toBeGreaterThan(0);
        expect(["orientativo", "relevante", "prioritario"]).toContain(rec.confidence);
        expect(rec.opportunity.recommendedFirstStep.length).toBeGreaterThan(0);
      }
      expect(r.intro.length).toBeGreaterThan(20);
      expect(r.shortTerm.length).toBeGreaterThan(10);
      expect(r.midTerm.length).toBeGreaterThan(10);
      expect(r.cta.label.length).toBeGreaterThan(5);
    }
  });

  it("perfil A: automatización operativa, solicitudes, asistentes o integraciones sencillas, sin exigir equipo técnico", () => {
    const r = generateResult(PROFILE_A, NOW);
    const cats = r.recommendations.map((x) => x.opportunity.category);
    for (const c of cats) expect(["automatizacion_operativa", "ia_conocimiento_soporte", "integraciones_orquestacion"]).toContain(c);
    for (const rec of r.recommendations) expect(rec.opportunity.technicalComplexity).toBeLessThanOrEqual(CAPACITY.sin_equipo + 1);
  });

  it("perfil B: operaciones, integración y reporting, con CTA de alta intención", () => {
    const r = generateResult(PROFILE_B, NOW);
    const cats = new Set(r.recommendations.map((x) => x.opportunity.category));
    for (const c of cats) expect(["automatizacion_operativa", "integraciones_orquestacion", "datos_reporting"]).toContain(c);
    expect(cats.size).toBeGreaterThanOrEqual(2);
    expect(r.cta.intent).toBe("muy_alta");
    expect(r.cta.label).toMatch(/demo/i);
  });

  it("perfil C: IA para desarrollo, documentación, testing o producto", () => {
    const r = generateResult(PROFILE_C, NOW);
    for (const rec of r.recommendations) expect(["ia_desarrollo", "producto_digital", "ia_conocimiento_soporte"]).toContain(rec.opportunity.category);
    expect(r.recommendations[0].opportunity.category).toBe("ia_desarrollo");
  });

  it("perfil D: recomendaciones orientativas, quick wins y CTA sin presión", () => {
    const r = generateResult(PROFILE_D, NOW);
    for (const rec of r.recommendations) {
      expect(rec.confidence).toBe("orientativo");
      expect(rec.opportunity.technicalComplexity).toBeLessThanOrEqual(3);
    }
    expect(r.score.range).toBe("exploracion");
    expect(r.cta.intent).toBe("baja");
    expect(r.cta.label).toMatch(/demo/i);
  });

  it("nunca recomienda más complejidad de la que la capacidad técnica permite", () => {
    for (const a of [PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_D, PROFILE_MANY]) {
      const r = generateResult(a, NOW);
      for (const rec of r.recommendations) expect(rec.opportunity.technicalComplexity).toBeLessThanOrEqual(CAPACITY[a.techCapacity] + 1);
    }
  });

  it("limita a dos oportunidades por categoría y explica citando respuestas", () => {
    const r = generateResult(PROFILE_MANY, NOW);
    const counts = new Map<string, number>();
    for (const rec of r.recommendations) counts.set(rec.opportunity.category, (counts.get(rec.opportunity.category) ?? 0) + 1);
    for (const n of counts.values()) expect(n).toBeLessThanOrEqual(2);
    for (const rec of r.recommendations) {
      if (rec.matchedFrictions.length > 0) {
        const first = rec.matchedFrictions[0]!;
        expect(rec.reasons.join(" ").toLowerCase()).toContain(frictionLabel(first).toLowerCase());
      }
    }
  });

  it("marca advertencia cuando la madurez queda fuera del rango de la oportunidad", () => {
    const a = { ...PROFILE_A, workLevel: "inicial" as const, dataLocation: "papel_chat" as const, frictions: ["desarrollo_software" as const, "testing_qa" as const], techCapacity: "especializado" as const };
    const r = generateResult(a, NOW);
    const order = ["explorador", "inicial", "en_adopcion", "integrador", "escalador"];
    for (const rec of r.recommendations) {
      const [lo, hi] = rec.opportunity.maturityRange;
      const m = order.indexOf(r.segment.maturity);
      const outside = m < order.indexOf(lo) || m > order.indexOf(hi);
      if (outside) expect(rec.warnings.length).toBeGreaterThan(0);
    }
    expect(r.warnings.length).toBeGreaterThan(0);
  });

  it("la complejidad del segmento final es la de la oportunidad principal", () => {
    const r = generateResult(PROFILE_B, NOW);
    expect(r.segment.complexity).toBe(r.recommendations[0].opportunity.complexityLabel);
  });

  it("es determinista", () => {
    expect(generateResult(PROFILE_MANY, NOW)).toEqual(generateResult({ ...PROFILE_MANY }, NOW));
    expect(generateResult(PROFILE_A, NOW).generatedAt).toBe(NOW.toISOString());
  });

  it("validateResult rechaza garantías, cifras de ROI, PII y complejidad excesiva", () => {
    const good = generateResult(PROFILE_A, NOW);
    expect(validateResult(good, PROFILE_A)).toEqual({ ok: true });

    const roi = structuredClone(good);
    roi.intro = "Garantizamos un 30% de ahorro";
    expect(validateResult(roi, PROFILE_A).ok).toBe(false);

    const pii = structuredClone(good);
    pii.shortTerm = "Escribe a ana@empresa.com";
    expect(validateResult(pii, PROFILE_A).ok).toBe(false);

    const heavy = structuredClone(good);
    heavy.recommendations[0].opportunity = { ...heavy.recommendations[0].opportunity, technicalComplexity: 5 };
    expect(validateResult(heavy, PROFILE_A).ok).toBe(false);

    const two = structuredClone(good) as unknown as { recommendations: unknown[] };
    two.recommendations = two.recommendations.slice(0, 2);
    expect(validateResult(two as unknown as typeof good, PROFILE_A).ok).toBe(false);
  });
});
