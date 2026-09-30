import { describe, expect, it } from "vitest";

import { normalisePhone, parseAudienceLines } from "../audience-lines";

/**
 * Spec 024 (Requisitos 1.2, 1.3): what the partner types becomes a list of
 * numbers, and what the API returns becomes text again.
 */

describe("audience lines · parse", () => {
  it("one number per line, with an optional name after the middle dot", () => {
    const out = parseAudienceLines("+56 9 9191 9125 · Daniel, ventas\n+34666261967\n");
    expect(out.errors).toEqual([]);
    expect(out.numbers).toEqual([
      { phone: "+56991919125", name: "Daniel, ventas" },
      { phone: "+34666261967", name: null },
    ]);
  });

  it("accepts commas between numbers when none carries a name", () => {
    const out = parseAudienceLines("+34666261967, 56931449225 ,+56 920 686 539");
    expect(out.errors).toEqual([]);
    expect(out.numbers.map((n) => n.phone)).toEqual(["+34666261967", "+56931449225", "+56920686539"]);
  });

  it("keeps the first of a repeated number and ignores blank lines", () => {
    const out = parseAudienceLines("\n+56991919125 · Daniel\n\n56 9 9191 9125\n");
    expect(out.numbers).toEqual([{ phone: "+56991919125", name: "Daniel" }]);
  });

  it("names the line that fails and keeps the good ones", () => {
    const out = parseAudienceLines("+56991919125\n12345\nhola · Ana\n+34666261967");
    expect(out.errors).toEqual([
      { line: 2, text: "12345" },
      { line: 3, text: "hola · Ana" },
    ]);
    expect(out.numbers.map((n) => n.phone)).toEqual(["+56991919125", "+34666261967"]);
  });
});

describe("audience lines · normalise", () => {
  it("strips spaces, dots, dashes and parentheses and adds the plus", () => {
    expect(normalisePhone("(56) 9-9191.9125")).toBe("+56991919125");
    expect(normalisePhone("+34 666 261 967")).toBe("+34666261967");
    expect(normalisePhone("123456")).toBeNull();
    expect(normalisePhone("+34 abc")).toBeNull();
  });
});
