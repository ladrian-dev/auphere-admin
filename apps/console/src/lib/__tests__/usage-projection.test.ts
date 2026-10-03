import { describe, expect, it } from "vitest";

import { meterGroups, percentOf, projectMonth, type SeriesPoint } from "../usage-projection";

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

describe("meterGroups (spec 028: the technical detail as a list)", () => {
  const points: SeriesPoint[] = [
    { day: "2026-10-01", by_meter: { "channel.message": 3, "llm.input_tokens": 900, "media.audio": 1 } },
    { day: "2026-10-02", by_meter: { "channel.message": 5, "llm.output_tokens": 120 } },
  ];
  it("groups by what it measures, model meters always present, cache included", () => {
    const groups = meterGroups(points, { "channel.message": 8, "llm.input_tokens": 900, "llm.output_tokens": 120, "media.audio": 1 });
    expect(groups.map((g) => g.key)).toEqual(["messages", "media", "model"]);
    const model = groups.find((g) => g.key === "model")!;
    expect(model.rows.map((r) => r.meter)).toEqual(["llm.input_tokens", "llm.output_tokens", "llm.cache_read", "llm.cache_write"]);
    expect(model.rows.find((r) => r.meter === "llm.cache_read")).toEqual({ meter: "llm.cache_read", total: 0, series: [0, 0] });
    expect(groups[0]!.rows[0]).toEqual({ meter: "channel.message", total: 8, series: [3, 5] });
  });
});
