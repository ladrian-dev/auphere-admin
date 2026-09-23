import { describe, expect, it } from "vitest";

import { barsFromSeries, cumulativeWithProjection, includedRemainingPercent, percentOf, projectMonth, seriesTotal, topMeters, type SeriesPoint } from "../usage-projection";

describe("projectMonth / percentOf (CP-22)", () => {
  it("projects linearly over the elapsed days", () => {
    expect(projectMonth(300, 10, 30)).toBe(900);
    expect(projectMonth(0, 5, 31)).toBe(0);
    expect(projectMonth(100, 0, 31)).toBe(100);
    expect(projectMonth(1000, 16, 31)).toBe(1937.5);
  });
  it("percent is null without a cap and rounded to 2 decimals", () => {
    expect(percentOf(30, 100)).toBe(30);
    expect(percentOf(1, 3)).toBe(33.33);
    expect(percentOf(30, null)).toBeNull();
    expect(percentOf(30, 0)).toBeNull();
  });
});

const points: SeriesPoint[] = [
  { day: "2026-08-01", by_meter: { "channel.message": 10, "llm.input_tokens": 500 } },
  { day: "2026-08-02", by_meter: { "channel.message": 20 } },
  { day: "2026-08-03", by_meter: { "media.image": 2 } },
];

describe("series shaping", () => {
  it("totals a meter and ranks meters", () => {
    expect(seriesTotal(points, "channel.message")).toBe(30);
    expect(topMeters(points, 2)).toEqual({ keys: ["llm.input_tokens", "channel.message"], hasOther: true });
  });
  it("folds the rest into `other`", () => {
    const rows = barsFromSeries(points, ["channel.message"]);
    expect(rows[0]).toEqual({ day: "2026-08-01", "channel.message": 10, other: 500 });
    expect(rows[2]).toEqual({ day: "2026-08-03", other: 2 });
  });
  it("draws the cumulative line and joins the projection at today", () => {
    const line = cumulativeWithProjection(points, "channel.message", "2026-08-01T00:00:00Z", 5, "2026-08-02");
    expect(line.map((p) => p.actual)).toEqual([10, 30, null, null, null]);
    // 30 over 2 days → 15/day; projection joins at today (30) then 45, 60, 75.
    expect(line.map((p) => p.projected)).toEqual([null, 30, 45, 60, 75]);
    expect(line.at(-1)?.projected).toBe(projectMonth(30, 2, 5));
  });
});

describe("includedRemainingPercent (bug: la tarjeta «Incluido restante» pintaba lo usado)", () => {
  it("a full pool reads 100 %, not 0 %", () => {
    expect(includedRemainingPercent({ included_remaining: 115_000, pool_size: 115_000, included_percent_used: 0 })).toBe(100);
  });
  it("is the complement of what the API says was used", () => {
    expect(includedRemainingPercent({ included_remaining: 30_000, pool_size: 100_000, included_percent_used: 70 })).toBe(30);
    expect(includedRemainingPercent({ included_remaining: 0, pool_size: 100_000, included_percent_used: 100 })).toBe(0);
    expect(includedRemainingPercent({ included_remaining: 1, pool_size: 3, included_percent_used: 66.67 })).toBe(33);
  });
  it("derives from the raw figures when the API omits the percentage", () => {
    expect(includedRemainingPercent({ included_remaining: 25_000, pool_size: 100_000 })).toBe(25);
  });
  it("clamps and treats a missing pool as nothing left", () => {
    expect(includedRemainingPercent({ included_remaining: 5, pool_size: 0 })).toBe(0);
    expect(includedRemainingPercent({ included_remaining: 5 })).toBe(0);
    expect(includedRemainingPercent({ included_remaining: 5, pool_size: 10, included_percent_used: -5 })).toBe(100);
  });
});
