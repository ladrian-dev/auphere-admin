import { describe, expect, it } from "vitest";

import { catalogHref, catalogState } from "../catalog-url";

describe("catalog address (spec 035)", () => {
  it("reads the three gestures and defaults to everything", () => {
    expect(catalogState({})).toEqual({ q: "", tab: "all", category: null });
    expect(catalogState({ q: " cal ", tab: "active", cat: "booking" })).toEqual({
      q: "cal",
      tab: "active",
      category: "booking",
    });
  });

  it("changes one gesture and keeps the rest", () => {
    expect(catalogHref("/connectors", "q=cal", { category: "booking" })).toBe("/connectors?q=cal&cat=booking");
    expect(catalogHref("/connectors", "q=cal&tab=active", { q: "", tab: "all" })).toBe("/connectors");
  });
});
