import { describe, expect, it } from "vitest";

import {
  actorLabel,
  formatMicros,
  formatMicrosExact,
  formatMicrosPlain,
  microsToInput,
  parseAmountToMicros,
  reasonError,
} from "../levers";

/** Spec 047 (T172): what the operator's levers share. */
describe("the operator's levers", () => {
  it("asks for a reason between 3 and 300 characters, like the API", () => {
    expect(reasonError("")).toBe("Hace falta el motivo.");
    expect(reasonError("  ok ")).toMatch(/al menos 3/);
    expect(reasonError("x".repeat(301))).toMatch(/como mucho 300/);
    expect(reasonError("El contrato lo pide")).toBeNull();
  });

  it("names who did it without the API's prefix", () => {
    expect(actorLabel("operator:ana@auphere.com")).toBe("ana@auphere.com");
    expect(actorLabel("console:maria@facelad.com")).toBe("maria@facelad.com");
    expect(actorLabel("companion:12345678-aaaa-bbbb-cccc-000000000000")).toBe("Companion (12345678)");
    expect(actorLabel("system")).toBe("system");
    expect(actorLabel(null)).toBe("—");
  });

  it("reads money written the Spanish or the English way as micros (1e-5 of the currency)", () => {
    expect(parseAmountToMicros("50")).toBe(5_000_000);
    expect(parseAmountToMicros("49,90")).toBe(4_990_000);
    expect(parseAmountToMicros("1.250,75")).toBe(125_075_000);
    expect(parseAmountToMicros("1,250.75")).toBe(125_075_000);
    expect(parseAmountToMicros("50 €")).toBe(5_000_000);
    expect(parseAmountToMicros("0")).toBe(0);
    for (const bad of ["", "abc", "-5", "5,123", "1e3"]) expect(parseAmountToMicros(bad)).toBeNull();
  });

  it("writes micros as the console writes money, and bare when the currency is unknown", () => {
    expect(formatMicros(5_000_000, "USD")).toMatch(/^50,00\sUSD$/);
    expect(formatMicros(4_990_000, "EUR")).toMatch(/^49,90\s€$/);
    expect(formatMicros(null, "USD")).toBe("—");
    expect(formatMicrosPlain(1)).toBe("0,00001");
    expect(formatMicrosPlain(-250_000)).toBe("-2,50");
    expect(formatMicrosPlain(null)).toBe("—");
  });

  it("writes the ledger's differences exact to the micro and in the currency the API names", () => {
    expect(formatMicrosExact(1, "EUR")).toBe("0,00001\u00a0€");
    expect(formatMicrosExact(5_000_000, "USD")).toBe("50,00\u00a0USD");
    expect(formatMicrosExact(null, "USD")).toBe("—");
  });

  it("puts a cap back in the amount field the way the parser reads it", () => {
    expect(microsToInput(5_000_000)).toBe("50,00");
    expect(microsToInput(125_075_000)).toBe("1250,75");
    expect(parseAmountToMicros(microsToInput(4_990_000))).toBe(4_990_000);
  });
});
