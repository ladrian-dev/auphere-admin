import { describe, expect, it } from "vitest";

import { formatUsd, parsePeriod, periodQuery } from "../period";

describe("Consumo periods (spec 038)", () => {
  it("defaults to the calendar month and ignores what it does not know", () => {
    expect(parsePeriod(undefined)).toBe("month");
    expect(parsePeriod("365")).toBe("month");
    expect(parsePeriod("30")).toBe("30");
  });

  it("asks the API for the month or for N days", () => {
    expect(periodQuery("month")).toEqual({ month: true });
    expect(periodQuery("7")).toEqual({ days: 7 });
  });

  it("keeps tiny model costs readable", () => {
    expect(formatUsd("0.0123")).toContain("0,0123");
    expect(formatUsd("407.82")).toContain("407,82");
    expect(formatUsd("nope")).toBe("—");
  });
});
