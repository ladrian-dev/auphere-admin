import { describe, expect, it } from "vitest";

import { DURATIONS, amountText, formatAmount, parseAmount } from "../services-model";

/**
 * Spec 047 (T060, requisito 11.7) — los precios con el formato y los decimales
 * de su moneda: los pesos chilenos sin decimales, los euros con dos.
 */

describe("formatAmount", () => {
  it("uses the decimals of the currency", () => {
    expect(formatAmount(15000, "CLP", 0, "es")).toBe("15.000 CLP");
    expect(formatAmount(1550, "EUR", 2, "es")).toBe("15,50 EUR");
    expect(formatAmount(1550, "EUR", 2, "en")).toBe("15.50 EUR");
    expect(formatAmount(1234567, "EUR", 2, "es")).toBe("12.345,67 EUR");
  });
});

describe("parseAmount", () => {
  it("reads what a person types into minor units", () => {
    expect(parseAmount("15,50", 2)).toBe(1550);
    expect(parseAmount("15.5", 2)).toBe(1550);
    expect(parseAmount("15", 2)).toBe(1500);
    expect(parseAmount("15.000", 0)).toBe(15000);
    expect(parseAmount("1.234,56", 2)).toBe(123456);
  });
  it("refuses what is not an amount", () => {
    expect(parseAmount("", 2)).toBeNull();
    expect(parseAmount("gratis", 2)).toBeNull();
    expect(parseAmount("-3", 2)).toBeNull();
    expect(parseAmount("15,555", 2)).toBeNull();
  });
  it("round-trips with amountText", () => {
    expect(parseAmount(amountText(1550, 2, "es"), 2)).toBe(1550);
    expect(parseAmount(amountText(15000, 0, "es"), 0)).toBe(15000);
  });
});

describe("durations", () => {
  it("go from 5 to 480 minutes in steps of 5", () => {
    expect(DURATIONS[0]).toBe(5);
    expect(DURATIONS.at(-1)).toBe(480);
    expect(DURATIONS.every((d) => d % 5 === 0)).toBe(true);
  });
});
