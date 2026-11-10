import { describe, expect, it } from "vitest";

import { auditQuery, moreLikeThisQuery, readFilters } from "../audit-query";

const now = new Date("2026-10-03T10:00:00Z");

describe("audit filters → API query", () => {
  it("drops what is empty or malformed", () => {
    const state = readFilters({ client: "lola", days: "13", after: "ayer" });
    expect(state.days).toBe("");
    expect(state.after).toBe("");
    expect(auditQuery(state, now)).toEqual({ client: "lola" });
  });

  it("sends the period and the person as the API takes them (spec 047, 49.1)", () => {
    expect(auditQuery(readFilters({ days: "7" }), now)).toEqual({ days: "7" });
    expect(auditQuery(readFilters({ days: "90", person: "ana@x.com" }), now)).toEqual({ days: "90", person: "ana@x.com" });
    // `actor` en una URL de antes sigue valiendo, y «Todo» no manda periodo.
    expect(auditQuery(readFilters({ actor: "ana@x.com" }), now)).toEqual({ person: "ana@x.com" });
  });

  it("«{n} más como esta» asks for the same person, action and client that day, without grouping", () => {
    expect(moreLikeThisQuery({ actor: "ana@x.com", action: "client.bag.assign", external_client_ref: "lola", at: "2026-10-27T15:04:00Z" })).toEqual({
      group: "false",
      person: "ana@x.com",
      action: "client.bag.assign",
      client: "lola",
      after: "2026-10-27T00:00:00Z",
      before: "2026-10-27T23:59:59Z",
      limit: "200",
    });
  });

  it("uses custom dates only when the period is custom", () => {
    expect(auditQuery(readFilters({ after: "2026-09-01" }), now)).toEqual({});
    expect(auditQuery(readFilters({ days: "custom", after: "2026-09-01", before: "2026-09-30" }), now)).toEqual({
      after: "2026-09-01T00:00:00Z",
      before: "2026-09-30T23:59:59Z",
    });
  });
});
