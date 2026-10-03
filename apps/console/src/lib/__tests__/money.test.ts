import { describe, expect, it } from "vitest";

import { formatMoney as fm, formatMoneyCompact as fmc, parseMoney } from "../money";

/** Intl puts a no-break space before the currency; the tests read plain text. */
const plain = (s: string) => s.replace(/\u00a0/g, " ");
const formatMoney = (...a: Parameters<typeof fm>) => plain(fm(...a));
const formatMoneyCompact = (...a: Parameters<typeof fmc>) => plain(fmc(...a));

describe("money (spec 027)", () => {
  it("formats cents as dollars, two decimals, by locale", () => {
    expect(formatMoney(1235, "es")).toBe("12,35 US$");
    expect(formatMoney(1235, "en")).toBe("$12.35");
    expect(formatMoney(0, "es")).toBe("0,00 US$");
    expect(formatMoney(null)).toBe("—");
  });

  it("compacts only large amounts", () => {
    expect(formatMoneyCompact(5_000, "es")).toBe("50,00 US$");
    expect(formatMoneyCompact(20_000_000, "es")).toBe("200 mil US$");
  });

  it("reads what the partner types, with comma or point", () => {
    expect(parseMoney("25,50")).toEqual({ kind: "money", cents: 2550 });
    expect(parseMoney("25.5")).toEqual({ kind: "money", cents: 2550 });
    expect(parseMoney("40")).toEqual({ kind: "money", cents: 4000 });
    expect(parseMoney(" 0 ")).toEqual({ kind: "money", cents: 0 });
    expect(parseMoney("")).toEqual({ kind: "empty" });
  });

  it("refuses what is not an amount of money", () => {
    for (const bad of ["-5", "4.555", "1.000,50", "abc", "1e3", "12,"]) {
      expect(parseMoney(bad)).toEqual({ kind: "invalid" });
    }
  });

  it("round-trips: what is typed is what comes back", () => {
    for (const typed of ["0", "0,01", "25,50", "999,99", "123456,78"]) {
      const parsed = parseMoney(typed);
      expect(parsed.kind).toBe("money");
      if (parsed.kind === "money") expect(formatMoney(parsed.cents, "es").replace(/\s?US\$/, "").replace(/\./g, "")).toBe(typed.includes(",") ? typed : `${typed},00`);
    }
  });
});
