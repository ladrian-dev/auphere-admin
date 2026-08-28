import { describe, expect, it } from "vitest";

import { parseCapInput } from "../parse-cap-input";

describe("parseCapInput (QA-26)", () => {
  it("treats empty / whitespace as empty (do not persist 0)", () => {
    expect(parseCapInput("")).toEqual({ kind: "empty" });
    expect(parseCapInput("   ")).toEqual({ kind: "empty" });
    expect(parseCapInput("\t\n")).toEqual({ kind: "empty" });
  });
  it("accepts explicit 0 and positive integers", () => {
    expect(parseCapInput("0")).toEqual({ kind: "cap", n: 0 });
    expect(parseCapInput("12")).toEqual({ kind: "cap", n: 12 });
    expect(parseCapInput(" 12 ")).toEqual({ kind: "cap", n: 12 });
  });
  it("rejects negatives, fractions and garbage", () => {
    expect(parseCapInput("-1")).toEqual({ kind: "invalid" });
    expect(parseCapInput("1.5")).toEqual({ kind: "invalid" });
    expect(parseCapInput("x")).toEqual({ kind: "invalid" });
  });
});
