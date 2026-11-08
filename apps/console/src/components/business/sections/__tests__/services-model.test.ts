import { describe, expect, it } from "vitest";

import { DURATION_MAX, DURATION_MIN, durationOk } from "@/lib/business-rules";

import { DURATIONS, priceText, samePrice } from "../services-model";

/**
 * Spec 047 (T060, requisito 11.7) y spec 056 (requisitos 5.2 y 13): los precios
 * con el formato del idioma de la persona (`lib/amount.ts`) y los decimales de
 * su moneda; las duraciones, las de las reglas compartidas.
 */
const WORDS = { free: "Gratis", none: "Sin precio" };

describe("priceText", () => {
  it("says free, no price or the amount in the person's language", () => {
    expect(priceText({ kind: "free" }, "CLP", "es", WORDS)).toBe("Gratis");
    expect(priceText({ kind: "none" }, "CLP", "es", WORDS)).toBe("Sin precio");
    expect(priceText({ kind: "amount" }, "CLP", "es", WORDS)).toBe("Sin precio");
    expect(priceText({ kind: "amount", amount_minor: 15000 }, "CLP", "es", WORDS).replace(/\s/g, " ")).toBe("15.000 CLP");
    expect(priceText({ kind: "amount", amount_minor: 1550 }, "EUR", "es", WORDS).replace(/\s/g, " ")).toBe("15,50 €");
    expect(priceText({ kind: "amount", amount_minor: 1000 }, "USD", "es", WORDS).replace(/\s/g, " ")).toBe("10,00 US$");
    expect(priceText({ kind: "amount", amount_minor: 1550 }, "EUR", "en", WORDS)).toBe("€15.50");
  });
});

describe("samePrice", () => {
  it("compares the kind and, for an amount, the amount", () => {
    expect(samePrice({ kind: "free" }, { kind: "free" })).toBe(true);
    expect(samePrice({ kind: "free" }, { kind: "none" })).toBe(false);
    expect(samePrice({ kind: "amount", amount_minor: 10 }, { kind: "amount", amount_minor: 10 })).toBe(true);
    expect(samePrice({ kind: "amount", amount_minor: 10 }, { kind: "amount", amount_minor: 11 })).toBe(false);
  });
});

describe("durations", () => {
  it("go from 5 to 480 minutes in steps of 5, the rules' ones", () => {
    expect(DURATIONS[0]).toBe(DURATION_MIN);
    expect(DURATIONS.at(-1)).toBe(DURATION_MAX);
    expect(DURATIONS).toHaveLength(96);
    expect(DURATIONS.every(durationOk)).toBe(true);
  });
});
