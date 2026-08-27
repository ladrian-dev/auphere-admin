import { describe, expect, it } from "vitest";

import { clientMatchesSearch } from "../client-search";

const farmacia = { name: "Demo Farmacia", external_client_ref: "demo-farmacia" };

describe("clientMatchesSearch (QA-01)", () => {
  it("zzzz matches nobody", () => {
    expect(clientMatchesSearch(farmacia, "zzzz")).toBe(false);
  });
  it("farmacia matches Demo Farmacia by name or ref", () => {
    expect(clientMatchesSearch(farmacia, "farmacia")).toBe(true);
    expect(clientMatchesSearch({ name: "Otro", external_client_ref: "demo-farmacia" }, "farmacia")).toBe(true);
  });
  it("empty / whitespace matches all", () => {
    expect(clientMatchesSearch(farmacia, "")).toBe(true);
    expect(clientMatchesSearch(farmacia, "   ")).toBe(true);
  });
  it("is case-insensitive on the ref", () => {
    expect(clientMatchesSearch(farmacia, "DEMO-FARMACIA")).toBe(true);
    expect(clientMatchesSearch(farmacia, "Demo-Farmacia")).toBe(true);
  });
});
