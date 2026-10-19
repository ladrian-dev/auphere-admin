import { describe, expect, it } from "vitest";

import { filterRows } from "../list-filter";

const rows = [
  { name: "Panadería La Espiga", slug: "la-espiga", status: "active", partner: "p1" },
  { name: "Mouna", slug: "mouna", status: "paused", partner: "p2" },
  { name: "Clínica Sol", slug: "clinica-sol", status: "active", partner: "p2" },
];
const text = (r: (typeof rows)[number]) => [r.name, r.slug];

describe("filterRows (spec 031, R4.2 / R5.2)", () => {
  it("matches any word ignoring accents and case", () => {
    expect(filterRows(rows, "panaderia", text).map((r) => r.slug)).toEqual(["la-espiga"]);
    expect(filterRows(rows, "CLÍNICA", text).map((r) => r.slug)).toEqual(["clinica-sol"]);
    expect(filterRows(rows, "mou", text).map((r) => r.slug)).toEqual(["mouna"]);
  });

  it("an empty query keeps every row", () => {
    expect(filterRows(rows, "  ", text)).toHaveLength(3);
  });

  it("combines the text with exact facets", () => {
    const facets = [
      { value: "active", of: (r: (typeof rows)[number]) => r.status },
      { value: "p2", of: (r: (typeof rows)[number]) => r.partner },
    ];
    expect(filterRows(rows, "", text, facets).map((r) => r.slug)).toEqual(["clinica-sol"]);
  });

  it("an empty facet value does not filter", () => {
    expect(filterRows(rows, "", text, [{ value: "", of: (r) => r.status }])).toHaveLength(3);
  });
});
