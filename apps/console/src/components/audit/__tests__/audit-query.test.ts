import { describe, expect, it } from "vitest";

import { auditQuery, readFilters } from "../audit-query";

const now = new Date("2026-10-03T10:00:00Z");

describe("audit filters → API query", () => {
  it("drops what is empty or malformed", () => {
    const state = readFilters({ client: "lola", days: "13", after: "ayer" });
    expect(state.days).toBe("");
    expect(state.after).toBe("");
    expect(auditQuery(state, now)).toEqual({ client: "lola" });
  });

  it("counts a period back from now", () => {
    expect(auditQuery(readFilters({ days: "7" }), now)).toEqual({ after: "2026-09-26T10:00:00.000Z" });
  });

  it("uses custom dates only when the period is custom", () => {
    expect(auditQuery(readFilters({ after: "2026-09-01" }), now)).toEqual({});
    expect(auditQuery(readFilters({ days: "custom", after: "2026-09-01", before: "2026-09-30" }), now)).toEqual({
      after: "2026-09-01T00:00:00Z",
      before: "2026-09-30T23:59:59Z",
    });
  });
});
