import { describe, expect, it } from "vitest";

import type { LiteBalance } from "@/lib/backend/lite";

import { balanceRunway, detailFamilies, runsOutDate, waitingHref } from "../lite-model";

const balance = (o: Partial<LiteBalance> = {}): LiteBalance => ({
  assigned: true,
  remaining_cents: 3013,
  cap_cents: 5000,
  days_left: 11.4,
  month_days_left: 24,
  runs_out_on: "2026-10-19",
  ...o,
});

/** Spec 045 (R4.3, contract §3): how far the balance goes, read the same on the Panel and in Consumo. */
describe("balanceRunway", () => {
  it("covers N of M days: N is the whole days it lasts, never more than the month has left", () => {
    expect(balanceRunway(balance())).toEqual({ days: 11, monthLeft: 24, tone: "warning" });
    expect(balanceRunway(balance({ days_left: 40 }))).toEqual({ days: 24, monthLeft: 24, tone: "positive" });
  });

  it("takes the month from the API (the business's zone), not from the browser's clock", () => {
    expect(balanceRunway(balance({ month_days_left: 3, days_left: 40 }))?.monthLeft).toBe(3);
  });

  it("alarms under 7 days, warns under 14, and is the primary tone otherwise", () => {
    expect(balanceRunway(balance({ days_left: 6.9 }))?.tone).toBe("danger");
    expect(balanceRunway(balance({ days_left: 7 }))?.tone).toBe("warning");
    expect(balanceRunway(balance({ days_left: 13.9 }))?.tone).toBe("warning");
    expect(balanceRunway(balance({ days_left: 14 }))?.tone).toBe("positive");
  });

  it("a used-up balance is an empty bar in the alarm tone", () => {
    expect(balanceRunway(balance({ remaining_cents: 0, days_left: 0, runs_out_on: "2026-10-08" }))).toEqual({
      days: 0,
      monthLeft: 24,
      tone: "danger",
    });
  });

  it("draws no bar without a pace to measure (no spend), without an allocation or without a month to divide", () => {
    expect(balanceRunway(balance({ days_left: null, runs_out_on: null }))).toBeNull();
    expect(balanceRunway(balance({ assigned: false, remaining_cents: null, cap_cents: null, days_left: null }))).toBeNull();
    expect(balanceRunway(balance({ month_days_left: 0 }))).toBeNull();
    expect(balanceRunway(null)).toBeNull();
  });
});

describe("runsOutDate", () => {
  const nov = new Date(2026, 10, 1, 12);
  const oct = new Date(2026, 9, 22, 12);

  it("reads the business's local date as that same day, in the person's language", () => {
    expect(runsOutDate("2026-11-02", "es", nov)).toBe("lunes 2");
    expect(runsOutDate("2026-11-02", "en", nov)).toBe("Monday 2");
  });

  it("names the month when it is not this one: «lunes 2» alone would read as this month", () => {
    expect(runsOutDate("2026-11-02", "es", oct)).toBe("lunes, 2 de noviembre");
    expect(runsOutDate("2026-11-02", "en", oct)).toBe("Monday 2 November");
  });

  it("is null when there is no date to give", () => {
    expect(runsOutDate(null, "es", oct)).toBeNull();
    expect(runsOutDate("not-a-date", "es", oct)).toBeNull();
  });
});

describe("waitingHref", () => {
  it("lands on the Inbox filtered to what waits, with the first one open", () => {
    expect(waitingHref("c-2")).toBe("/inbox?filter=waiting&c=c-2");
    expect(waitingHref(null)).toBe("/inbox?filter=waiting");
  });
});

/** Spec 045 (R6.3): the technical detail in three families, one channel row. */
describe("detailFamilies", () => {
  it("adds each meter to its family", () => {
    expect(
      detailFamilies({
        "channel.message": 1284,
        "llm.input_tokens": 120_000,
        "llm.output_tokens": 30_000,
        "llm.cache_read": 0,
        "media.image": 9,
        "media.document": 3,
      }),
    ).toEqual({ messages: 1284, model: 150_000, media: 12, other: null });
  });

  it("says nothing of «other» unless an unknown meter is there", () => {
    expect(detailFamilies({ "channel.message": 3 }).other).toBeNull();
    expect(detailFamilies({ "channel.message": 3, "voice.minutes": 4, "web.search": 2 }).other).toBe(6);
  });

  it("an empty period is three zeros, not missing columns", () => {
    expect(detailFamilies({})).toEqual({ messages: 0, model: 0, media: 0, other: null });
  });
});
