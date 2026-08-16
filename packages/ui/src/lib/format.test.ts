import { describe, expect, it } from "vitest";

import { formatBytes, formatCurrency, formatDuration, formatLatency, formatNumber, formatPercent, formatRelative } from "./format";

describe("format (Intl, locale-aware)", () => {
  it("numbers follow the locale", () => {
    expect(formatNumber(1234567.891, "es")).toBe("1.234.567,891");
    expect(formatNumber(1234567.891, "en")).toBe("1,234,567.891");
    expect(formatNumber(null)).toBe("—");
  });
  it("currency and percent", () => {
    expect(formatCurrency(1234.5, "USD", "en")).toBe("$1,234.50");
    expect(formatPercent(0.825, "en")).toBe("83%");
  });
  it("relative time uses Intl.RelativeTimeFormat", () => {
    const now = new Date("2026-08-15T12:00:00Z");
    expect(formatRelative("2026-08-15T11:00:00Z", "en", now)).toBe("1 hour ago");
    expect(formatRelative("2026-08-14T12:00:00Z", "es", now)).toBe("ayer");
  });
  it("durations, latency, bytes", () => {
    expect(formatDuration(45, "en")).toBe("45 s");
    expect(formatDuration(3600 * 3, "en")).toBe("3 h");
    expect(formatLatency(423, "en")).toBe("423 ms");
    expect(formatLatency(1250, "en")).toBe("1.3 s");
    expect(formatBytes(2048, "en")).toBe("2 kB");
  });
});
