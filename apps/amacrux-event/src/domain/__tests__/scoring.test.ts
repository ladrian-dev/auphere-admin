import { describe, expect, it } from "vitest";

import { rangeFor, scoreAnswers, tierFor, CAPACITY_POINTS, GOAL_IMPACT, INTENT_POINTS, INVESTMENT_POINTS, URGENCY_POINTS, WORK_LEVEL_POINTS } from "../scoring";
import { segmentAnswers } from "../segmentation";
import { PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_D } from "./fixtures";

const score = (a: typeof PROFILE_A) => scoreAnswers(a, segmentAnswers(a));

describe("scoring", () => {
  it("las tablas respetan los máximos del brief", () => {
    expect(Math.max(...Object.values(URGENCY_POINTS))).toBe(15);
    expect(Math.max(...Object.values(CAPACITY_POINTS))).toBe(15);
    expect(Math.max(...Object.values(INVESTMENT_POINTS))).toBe(15);
    expect(Math.max(...Object.values(WORK_LEVEL_POINTS))).toBe(10);
    expect(Math.max(...Object.values(INTENT_POINTS))).toBe(10);
    expect(Math.max(...Object.values(GOAL_IMPACT))).toBeLessThanOrEqual(10);
  });

  it("el total es la suma del desglose y cada factor respeta su rango", () => {
    for (const a of [PROFILE_A, PROFILE_B, PROFILE_C, PROFILE_D]) {
      const s = score(a);
      const sum = Object.values(s.breakdown).reduce((x, y) => x + y, 0);
      expect(s.total).toBe(sum);
      expect(s.total).toBeGreaterThanOrEqual(0);
      expect(s.total).toBeLessThanOrEqual(100);
      expect(s.breakdown.problemClarity).toBeLessThanOrEqual(20);
      expect(s.breakdown.impact).toBeLessThanOrEqual(20);
      expect(s.breakdown.urgency).toBeLessThanOrEqual(15);
      expect(s.breakdown.capacity).toBeLessThanOrEqual(15);
      expect(s.breakdown.maturity).toBeLessThanOrEqual(10);
      expect(s.breakdown.fit).toBeLessThanOrEqual(10);
      expect(s.breakdown.intent).toBeLessThanOrEqual(10);
    }
  });

  it("rangos y etiquetas internas", () => {
    expect(rangeFor(0)).toBe("exploracion");
    expect(rangeFor(29)).toBe("exploracion");
    expect(rangeFor(30)).toBe("oportunidad_inicial");
    expect(rangeFor(54)).toBe("oportunidad_inicial");
    expect(rangeFor(55)).toBe("oportunidad_prioritaria");
    expect(rangeFor(74)).toBe("oportunidad_prioritaria");
    expect(rangeFor(75)).toBe("alta_intencion");
    expect(rangeFor(100)).toBe("alta_intencion");
    expect(tierFor("exploracion")).toBe("frio");
    expect(tierFor("alta_intencion")).toBe("muy_caliente");
  });

  it("vectores fijos para los perfiles A–D", () => {
    expect(score(PROFILE_A).range).toBe("oportunidad_prioritaria");
    expect(score(PROFILE_B).range).toBe("alta_intencion");
    expect(score(PROFILE_C).range).toBe("alta_intencion");
    expect(score(PROFILE_D).range).toBe("exploracion");
    expect(score(PROFILE_D).breakdown.problemClarity).toBe(4);
    expect(score(PROFILE_A).breakdown.problemClarity).toBe(20);
  });

  it("es reproducible", () => {
    expect(score(PROFILE_B)).toEqual(score({ ...PROFILE_B }));
  });
});
