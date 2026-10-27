import { describe, expect, it } from "vitest";

import type { Hours } from "@/lib/backend/business-sections";

import {
  MAX_SHIFTS,
  blockRows,
  blocksLoss,
  bodyFromDraft,
  draftFromHours,
  isOvernight,
  toBlocks,
  validateDraft,
} from "../hours-model";

/**
 * Spec 047 (T060, requisito 10) — el modelo del editor del horario: por bloques
 * o día por día, hasta 6 turnos, nocturnos («cierra al día siguiente») y lo que
 * se perdería al pasar a bloques (10.6).
 */

const shift = (open: string, close: string) => ({ open, close, overnight: isOvernight(open, close) });
const HOURS: Hours = {
  revision: 3,
  state: "complete",
  allowed: ["edit"],
  location_id: null,
  inherits: false,
  layout: "daily",
  days: {
    mon: [shift("09:00", "14:00"), shift("16:00", "20:00")],
    tue: [shift("10:00", "14:00")],
    wed: [shift("09:00", "14:00"), shift("16:00", "20:00")],
    thu: [],
    fri: [shift("20:00", "02:00")],
    sat: [shift("00:00", "24:00")],
    sun: [],
  },
  label: "Abrimos…",
};

describe("isOvernight", () => {
  it("a close at or before the opening ends the next day", () => {
    expect(isOvernight("22:00", "02:00")).toBe(true);
    expect(isOvernight("10:00", "10:00")).toBe(true);
    expect(isOvernight("09:00", "14:00")).toBe(false);
  });
  it("midnight and 24 hours are not «next day»", () => {
    expect(isOvernight("20:00", "00:00")).toBe(false);
    expect(isOvernight("00:00", "24:00")).toBe(false);
    expect(isOvernight("00:00", "00:00")).toBe(false);
  });
});

describe("the draft", () => {
  it("reads the section and writes back what the API takes", () => {
    const draft = draftFromHours(HOURS);
    expect(draft.layout).toBe("daily");
    expect(draft.days.mon.map((s) => [s.open, s.close])).toEqual([
      ["09:00", "14:00"],
      ["16:00", "20:00"],
    ]);
    expect(new Set(draft.days.mon.map((s) => s.key)).size).toBe(2);
    const body = bodyFromDraft(draft);
    expect(body).toEqual({
      layout: "daily",
      days: {
        mon: [
          { open: "09:00", close: "14:00" },
          { open: "16:00", close: "20:00" },
        ],
        tue: [{ open: "10:00", close: "14:00" }],
        wed: [
          { open: "09:00", close: "14:00" },
          { open: "16:00", close: "20:00" },
        ],
        thu: [],
        fri: [{ open: "20:00", close: "02:00" }],
        sat: [{ open: "00:00", close: "24:00" }],
        sun: [],
      },
    });
  });

  it("starts empty without hours", () => {
    const draft = draftFromHours({ ...HOURS, layout: null, label: null, days: { mon: [], tue: [], wed: [], thu: [], fri: [], sat: [], sun: [] } });
    expect(draft.layout).toBe("blocks");
    expect(Object.values(draft.days).every((d) => d.length === 0)).toBe(true);
  });
});

describe("blocks", () => {
  it("are Monday to Friday, Saturday and Sunday", () => {
    expect(blockRows("blocks").map((r) => r.days)).toEqual([["mon", "tue", "wed", "thu", "fri"], ["sat"], ["sun"]]);
    expect(blockRows("daily")).toHaveLength(7);
  });

  it("say which weekdays would be lost (requisito 10.6)", () => {
    const draft = draftFromHours(HOURS);
    expect(blocksLoss(draft)).toEqual(["tue", "thu", "fri"]);
    const blocks = toBlocks(draft);
    expect(blocks.layout).toBe("blocks");
    for (const d of ["tue", "wed", "thu", "fri"] as const) {
      expect(blocks.days[d].map((s) => [s.open, s.close])).toEqual(blocks.days.mon.map((s) => [s.open, s.close]));
    }
    expect(blocks.days.sat).toEqual(draft.days.sat);
    expect(blocksLoss(blocks)).toEqual([]);
  });
});

describe("validation", () => {
  it("allows up to six shifts a day", () => {
    const draft = draftFromHours(HOURS);
    const seven = Array.from({ length: MAX_SHIFTS + 1 }, (_, i) => ({ key: `k${i}`, open: `0${i + 1}:00`, close: `0${i + 1}:30` }));
    expect(validateDraft({ ...draft, days: { ...draft.days, mon: seven } })).toEqual([{ day: "mon", code: "too_many_shifts" }]);
    expect(validateDraft(draft)).toEqual([]);
  });
  it("refuses a time that is not HH:MM", () => {
    const draft = draftFromHours(HOURS);
    expect(validateDraft({ ...draft, days: { ...draft.days, tue: [{ key: "x", open: "9", close: "14:00" }] } })).toEqual([
      { day: "tue", code: "invalid_time" },
    ]);
  });
});
