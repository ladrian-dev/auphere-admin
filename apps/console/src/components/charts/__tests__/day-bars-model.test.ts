import { describe, expect, it } from "vitest";

import { keepDayLabelWhenNarrow, showDayLabel } from "../day-bars-model";

const labelled = (count: number) => Array.from({ length: count }, (_, i) => i).filter((i) => showDayLabel(i, count));

describe("day labels", () => {
  it("prints every day up to two weeks, and about ten beyond, always today", () => {
    expect(labelled(7)).toHaveLength(7);
    expect(labelled(30)).toHaveLength(10);
    expect(labelled(30)).toContain(29);
  });

  // Spec 030 (T105): ten labels of «20 sept» do not fit in a 360 px phone.
  it("keeps one of every two printed labels when the chart is narrow, today included", () => {
    const kept = labelled(30).filter((i) => keepDayLabelWhenNarrow(i, 30));
    expect(kept).toHaveLength(5);
    expect(kept).toContain(29);
  });

  it("keeps every label of a short chart, which already fits", () => {
    expect(labelled(7).every((i) => keepDayLabelWhenNarrow(i, 7))).toBe(true);
  });
});
