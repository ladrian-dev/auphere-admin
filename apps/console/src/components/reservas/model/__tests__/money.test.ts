import { describe, expect, it } from "vitest";

import { PRICE_CURRENCIES } from "@/components/clients/client-modal-model";

import { minorDigits, parsePrice } from "../money";

describe("minorDigits (spec 055)", () => {
  it("agrees with the API's table (`services_catalog.ZERO_DECIMALS`) for every currency offered", () => {
    const zero = PRICE_CURRENCIES.filter((c) => minorDigits(c) === 0);
    expect([...zero].sort()).toEqual(["CLP", "ISK", "PYG"]);
    expect(PRICE_CURRENCIES.every((c) => [0, 2].includes(minorDigits(c)))).toBe(true);
  });

  it("takes decimals only in a currency that has them", () => {
    expect(parsePrice("15,50", "USD")).toEqual({ kind: "ok", minor: 1550 });
    expect(parsePrice("15,50", "CLP")).toEqual({ kind: "invalid" });
  });
});
