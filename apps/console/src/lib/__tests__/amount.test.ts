import { describe, expect, it } from "vitest";

import { minorDigits as reservasMinorDigits } from "@/components/reservas/model/money";

import { AMOUNT_MAX_MINOR } from "../business-rules";
import { amountInput, amountParts, formatAmount as fa, minorDigits, parseAmount } from "../amount";

/** Intl pone un espacio duro antes de la moneda; las pruebas leen texto plano. */
const plain = (s: string) => s.replace(/[  ]/g, " ");
const formatAmount = (...a: Parameters<typeof fa>) => plain(fa(...a));

/**
 * Spec 056 (T011; requisitos 13.1 y 13.2): un solo formato de dinero, el del
 * idioma de la persona, y campos que aceptan coma o punto.
 */
describe("amount (spec 056)", () => {
  it("minorDigits es la tabla ISO 4217 de la API (`services_catalog.exponent`), no la de Intl", () => {
    expect(minorDigits("EUR")).toBe(2);
    expect(minorDigits("usd")).toBe(2);
    // Intl da 0 decimales al peso colombiano; la unidad menor guardada tiene 2.
    expect(minorDigits("COP")).toBe(2);
    expect(minorDigits("CLP")).toBe(0);
    expect(minorDigits("KWD")).toBe(3);
    // Reservas lee la misma tabla.
    expect(reservasMinorDigits).toBe(minorDigits);
  });

  describe("formatAmount: Intl con el idioma de la persona (13.1)", () => {
    it("en español", () => {
      expect(formatAmount({ amount_minor: 1000, currency: "USD" }, "es")).toBe("10,00 US$");
      expect(formatAmount({ amount_minor: 1550, currency: "EUR" }, "es")).toBe("15,50 €");
      // Intl en español no agrupa cuatro cifras: es el formato del idioma.
      expect(formatAmount({ amount_minor: 150_000, currency: "EUR" }, "es")).toBe("1500,00 €");
      expect(formatAmount({ amount_minor: 123_456_750, currency: "EUR" }, "es")).toBe("1.234.567,50 €");
      expect(formatAmount({ amount_minor: 1_000_000, currency: "COP" }, "es")).toBe("10.000,00 COP");
      expect(formatAmount({ amount_minor: 15_000, currency: "CLP" }, "es")).toBe("15.000 CLP");
    });

    it("en inglés", () => {
      expect(formatAmount({ amount_minor: 1000, currency: "USD" }, "en")).toBe("$10.00");
      expect(formatAmount({ amount_minor: 150_000, currency: "EUR" }, "en")).toBe("€1,500.00");
      expect(formatAmount({ amount_minor: 1_000_000, currency: "COP" }, "en")).toBe("COP 10,000.00");
      expect(formatAmount({ amount_minor: 15_000, currency: "CLP" }, "en")).toBe("CLP 15,000");
    });

    it("el tope se escribe entero, y lo que no es un importe no rompe", () => {
      expect(formatAmount({ amount_minor: AMOUNT_MAX_MINOR, currency: "CLP" }, "es")).toBe("1.000.000.000.000 CLP");
      expect(formatAmount({ amount_minor: 0, currency: "EUR" }, "es")).toBe("0,00 €");
      expect(formatAmount({ amount_minor: Number.NaN, currency: "EUR" }, "es")).toBe("—");
      // Una moneda que Intl no acepta: el número del idioma y el código.
      expect(formatAmount({ amount_minor: 1550, currency: "EURO" }, "es")).toBe("15,50 EURO");
    });
  });

  describe("parseAmount: coma o punto (13.2)", () => {
    it("con decimales, coma o punto", () => {
      expect(parseAmount("15,50", "EUR")).toEqual({ kind: "ok", minor: 1550 });
      expect(parseAmount("15.5", "EUR")).toEqual({ kind: "ok", minor: 1550 });
      expect(parseAmount("15", "USD")).toEqual({ kind: "ok", minor: 1500 });
      expect(parseAmount("0", "USD")).toEqual({ kind: "ok", minor: 0 });
      expect(parseAmount(" 10,00 ", "USD")).toEqual({ kind: "ok", minor: 1000 });
    });

    it("con miles: «1.234,56» (es), «1,234.56» (en), y un punto con tres cifras es de miles", () => {
      expect(parseAmount("1.234,56", "EUR")).toEqual({ kind: "ok", minor: 123_456 });
      expect(parseAmount("1,234.56", "USD")).toEqual({ kind: "ok", minor: 123_456 });
      expect(parseAmount("1.234", "EUR")).toEqual({ kind: "ok", minor: 123_400 });
      expect(parseAmount("1.234.567", "COP")).toEqual({ kind: "ok", minor: 123_456_700 });
      expect(parseAmount("1,234,567", "USD")).toEqual({ kind: "ok", minor: 123_456_700 });
      expect(parseAmount("1 234,56", "EUR")).toEqual({ kind: "ok", minor: 123_456 });
    });

    it("una moneda sin decimales: los separadores son de miles", () => {
      expect(parseAmount("15.000", "CLP")).toEqual({ kind: "ok", minor: 15_000 });
      expect(parseAmount("15,000", "CLP")).toEqual({ kind: "ok", minor: 15_000 });
      expect(parseAmount("15000", "CLP")).toEqual({ kind: "ok", minor: 15_000 });
      expect(parseAmount("15,50", "CLP")).toEqual({ kind: "invalid", code: "price_invalid" });
    });

    it("con tres decimales, el punto con tres cifras es decimal", () => {
      expect(parseAmount("1.234", "KWD")).toEqual({ kind: "ok", minor: 1234 });
      expect(parseAmount("1,234.567", "KWD")).toEqual({ kind: "ok", minor: 1_234_567 });
    });

    it("vacío no es cero", () => {
      expect(parseAmount("", "EUR")).toEqual({ kind: "empty" });
      expect(parseAmount("   ", "EUR")).toEqual({ kind: "empty" });
    });

    it("lo que no es un importe", () => {
      for (const bad of ["-5", "abc", "1e3", "12,", ",5", "15,555", "1.2.3", "1.234,567.89", "1,23,456", "€10"]) {
        expect(parseAmount(bad, "EUR")).toEqual({ kind: "invalid", code: "price_invalid" });
      }
    });

    it("el tope es 10¹² unidades menores: más es amount_too_large", () => {
      expect(parseAmount("10000000000", "USD")).toEqual({ kind: "ok", minor: AMOUNT_MAX_MINOR });
      expect(parseAmount("10000000000,01", "USD")).toEqual({ kind: "invalid", code: "amount_too_large" });
      expect(parseAmount("1.000.000.000.000", "CLP")).toEqual({ kind: "ok", minor: AMOUNT_MAX_MINOR });
      expect(parseAmount("1.000.000.000.001", "CLP")).toEqual({ kind: "invalid", code: "amount_too_large" });
      expect(parseAmount("9".repeat(40), "EUR")).toEqual({ kind: "invalid", code: "amount_too_large" });
    });
  });

  describe("amountInput: el campo, con el separador del idioma (13.2)", () => {
    it("sin moneda y sin miles", () => {
      expect(amountInput(1550, "EUR", "es")).toBe("15,50");
      expect(amountInput(1550, "EUR", "en")).toBe("15.50");
      expect(amountInput(123_456, "USD", "es")).toBe("1234,56");
      expect(amountInput(1_000_000, "COP", "en")).toBe("10000.00");
      expect(amountInput(15_000, "CLP", "es")).toBe("15000");
      expect(amountInput(null, "EUR", "es")).toBe("");
    });

    it("lo que enseña el campo se lee igual", () => {
      for (const locale of ["es", "en"] as const) {
        for (const [minor, currency] of [
          [0, "EUR"],
          [1550, "EUR"],
          [123_456, "USD"],
          [1_000_000, "COP"],
          [15_000, "CLP"],
          [1_234_567, "KWD"],
          [AMOUNT_MAX_MINOR, "USD"],
        ] as const) {
          expect(parseAmount(amountInput(minor, currency, locale), currency)).toEqual({ kind: "ok", minor });
        }
      }
    });
  });
});

/** Spec 056 (13.1, T053): «Gasto del mes» pinta las partes del mismo formato. */
describe("amountParts", () => {
  it("joined, they are formatAmount", () => {
    for (const [minor, currency, locale] of [
      [1626, "USD", "es"],
      [1626, "USD", "en"],
      [15000, "CLP", "es"],
      [123456, "EUR", "es"],
    ] as const) {
      expect(amountParts({ amount_minor: minor, currency }, locale).map((p) => p.value).join("")).toBe(fa({ amount_minor: minor, currency }, locale));
    }
    expect(amountParts({ amount_minor: 1626, currency: "USD" }, "es").some((p) => p.type === "fraction" && p.value === "26")).toBe(true);
  });
});
