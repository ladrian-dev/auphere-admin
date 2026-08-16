import { describe, expect, it } from "vitest";

import { diffLines } from "../prompt-diff";

describe("diffLines", () => {
  it("marks additions and deletions", () => {
    const out = diffLines("a\nb\nc", "a\nx\nc");
    expect(out.map((l) => l.kind)).toEqual(["same", "del", "add", "same"]);
  });
  it("identical texts are all same", () => {
    expect(diffLines("a\nb", "a\nb").every((l) => l.kind === "same")).toBe(true);
  });
});
