import { describe, expect, it } from "vitest";

import { FRICTIONS, GOALS, PROFILES } from "../enums";
import { ALL_QUESTIONS, TOTAL_ESTIMATED_SECONDS, TOTAL_QUESTIONS, remainingSeconds } from "../questions";

describe("definición de preguntas", () => {
  it("son 12 preguntas, una por pantalla, con etiquetas cortas", () => {
    expect(TOTAL_QUESTIONS).toBe(12);
    for (const q of ALL_QUESTIONS) for (const o of q.options) expect(o.label.split(" ").length, `${q.id}:${o.value}`).toBeLessThanOrEqual(4);
  });

  it("los máximos de selección múltiple son 3 y 2", () => {
    expect(ALL_QUESTIONS.find((q) => q.id === "frictions")?.max).toBe(3);
    expect(ALL_QUESTIONS.find((q) => q.id === "goals")?.max).toBe(2);
    expect(ALL_QUESTIONS.find((q) => q.id === "frictions")?.options.map((o) => o.value).sort()).toEqual([...FRICTIONS].sort());
    expect(ALL_QUESTIONS.find((q) => q.id === "goals")?.options.map((o) => o.value).sort()).toEqual([...GOALS].sort());
  });

  it("la pregunta de rol ofrece todos los perfiles del enum", () => {
    expect(ALL_QUESTIONS.find((q) => q.id === "profile")?.options.map((o) => o.value).sort()).toEqual([...PROFILES].sort());
  });

  it("no muestra la palabra 'madurez' y todo tiene etiqueta", () => {
    const text = JSON.stringify(ALL_QUESTIONS).toLowerCase();
    expect(text).not.toContain("madurez");
    for (const q of ALL_QUESTIONS) for (const o of q.options) expect(o.label.trim().length).toBeGreaterThan(0);
  });

  it("el tiempo estimado total está entre 2 y 4 minutos", () => {
    expect(TOTAL_ESTIMATED_SECONDS).toBeGreaterThanOrEqual(120);
    expect(TOTAL_ESTIMATED_SECONDS).toBeLessThanOrEqual(240);
    expect(remainingSeconds("profile")).toBe(TOTAL_ESTIMATED_SECONDS);
    expect(remainingSeconds("investment")).toBeLessThan(remainingSeconds("goals"));
  });
});
