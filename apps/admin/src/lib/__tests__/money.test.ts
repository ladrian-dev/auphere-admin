import { describe, expect, it } from "vitest";

import { MAX_TOPUP_CENTS, parseUsdToCents } from "../money";

describe("parseUsdToCents (spec 033, R1.2)", () => {
  it("reads dollars written the Spanish or the English way", () => {
    expect(parseUsdToCents("50")).toBe(5_000);
    expect(parseUsdToCents("50,5")).toBe(5_050);
    expect(parseUsdToCents("50.25")).toBe(5_025);
    expect(parseUsdToCents("1.250,75")).toBe(125_075);
    expect(parseUsdToCents("1,250.75")).toBe(125_075);
    expect(parseUsdToCents("US$ 12")).toBe(1_200);
  });

  it("refuses what is not an amount", () => {
    for (const bad of ["", "abc", "-5", "5,123", "0", "0,00", "1e3"]) {
      expect(parseUsdToCents(bad)).toBeNull();
    }
  });

  it("caps a single top-up at US$ 10 000", () => {
    expect(parseUsdToCents("10000")).toBe(MAX_TOPUP_CENTS);
    expect(parseUsdToCents("10000,01")).toBeNull();
  });
});
