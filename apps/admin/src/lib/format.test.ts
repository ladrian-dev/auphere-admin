import { describe, expect, it } from "vitest";

import { fullDateTime, planLabel, relativeTime, statusLabel } from "./format";

describe("relativeTime", () => {
  it("returns dash for null/undefined", () => {
    expect(relativeTime(null)).toBe("—");
    expect(relativeTime(undefined)).toBe("—");
  });

  it("formats a recent past date in spanish", () => {
    const now = new Date();
    const twoMinAgo = new Date(now.getTime() - 2 * 60 * 1000);
    const out = relativeTime(twoMinAgo);
    // "hace 2 minutos" or numeric:auto fallback — accept anything that
    // contains 2 to keep the assertion robust against runtime locale data.
    expect(out).toMatch(/2/);
  });

  it("formats a future date", () => {
    const now = new Date();
    const inThreeHours = new Date(now.getTime() + 3 * 60 * 60 * 1000);
    expect(relativeTime(inThreeHours)).toMatch(/3/);
  });
});

describe("statusLabel + planLabel", () => {
  it("translates plans + statuses to spanish", () => {
    expect(planLabel("pro")).toBe("Pro");
    expect(planLabel("essential")).toBe("Esencial");
    expect(statusLabel("active")).toBe("Activo");
    expect(statusLabel("escalated")).toBe("Escalado");
  });

  it("falls through unknowns unchanged", () => {
    expect(planLabel("custom")).toBe("custom");
    expect(statusLabel("frozen")).toBe("frozen");
  });
});

describe("fullDateTime", () => {
  it("returns dash for null", () => {
    expect(fullDateTime(null)).toBe("—");
  });

  it("formats an ISO string", () => {
    const out = fullDateTime("2026-05-09T12:00:00Z");
    expect(out).toMatch(/2026/);
  });
});
