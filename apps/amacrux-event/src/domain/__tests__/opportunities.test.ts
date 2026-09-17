import { describe, expect, it } from "vitest";

import { OPPORTUNITY_CATEGORIES, PROFILE_SEGMENTS } from "../enums";
import { DEFAULTS_BY_PROFILE, OPPORTUNITIES } from "../opportunities";

const FORBIDDEN = /\d+\s?%|€|\$|garantiz|ROI|retorno de (la )?inversi/i;

describe("catálogo de oportunidades", () => {
  it("tiene al menos 24 entradas con ids únicos", () => {
    expect(OPPORTUNITIES.length).toBeGreaterThanOrEqual(24);
    expect(new Set(OPPORTUNITIES.map((o) => o.id)).size).toBe(OPPORTUNITIES.length);
    for (const o of OPPORTUNITIES) expect(o.id).toMatch(/^[a-z0-9-]{1,64}$/);
  });

  it("cubre las 8 categorías con al menos 3 oportunidades cada una", () => {
    for (const c of OPPORTUNITY_CATEGORIES) {
      expect(OPPORTUNITIES.filter((o) => o.category === c).length, c).toBeGreaterThanOrEqual(3);
    }
  });

  it("no promete cifras de ahorro, ROI ni garantías", () => {
    for (const o of OPPORTUNITIES) {
      const text = [o.title, o.problemSolved, o.howItWorks, o.benefitDescription, o.recommendedFirstStep, o.amacruxFit, o.warning ?? "", o.commercialCta, ...o.requiredInputs].join(" ");
      expect(text, o.id).not.toMatch(FORBIDDEN);
    }
  });

  it("tiene todos los campos obligatorios rellenos y coherentes", () => {
    for (const o of OPPORTUNITIES) {
      for (const f of ["title", "problemSolved", "howItWorks", "benefitDescription", "recommendedFirstStep", "amacruxFit", "commercialCta", "expectedTimeToPilot"] as const) {
        expect(o[f].trim().length, `${o.id}.${f}`).toBeGreaterThan(10);
      }
      expect(o.problemSignals.length + o.desiredOutcomes.length, o.id).toBeGreaterThan(0);
      expect(o.requiredInputs.length, o.id).toBeGreaterThan(0);
      expect(o.relatedTools.length, o.id).toBeGreaterThan(0);
      expect(o.technicalComplexity).toBeGreaterThanOrEqual(1);
      expect(o.technicalComplexity).toBeLessThanOrEqual(5);
    }
  });

  it("tiene al menos 3 recomendaciones por defecto para cada perfil, todas del catálogo", () => {
    const ids = new Set(OPPORTUNITIES.map((o) => o.id));
    for (const p of PROFILE_SEGMENTS) {
      const defaults = DEFAULTS_BY_PROFILE[p];
      expect(defaults.length, p).toBeGreaterThanOrEqual(3);
      for (const id of defaults) expect(ids.has(id), `${p}:${id}`).toBe(true);
    }
  });
});
