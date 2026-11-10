import { describe, expect, it } from "vitest";

import { DAYS } from "@/lib/backend/business-sections";
import { DURATIONS } from "@/components/business/sections/services-model";

import {
  AMOUNT_MAX_MINOR,
  CATEGORY_MAX,
  DURATION_MAX,
  DURATION_MIN,
  DURATION_STEP,
  MAX_SHIFTS_PER_DAY,
  MINUTES_PER_DAY,
  NAME_MAX,
  NAME_MIN,
  PRICE_KINDS,
  TIME_STEP,
  WEEK_DAYS,
  checkCategory,
  checkDay,
  checkDuration,
  checkName,
  checkPrice,
  checkWeek,
  durationOk,
  onStep,
  shiftMinutes,
  timeMinutes,
} from "../business-rules";

/**
 * Spec 056 (T009; requisitos 5.1 y 5.2): las mismas reglas que la API
 * (`apps/api/src/nexus_api/services/business/rules.py`), con los mismos casos que
 * `apps/api/tests/unit/test_business_rules.py`. Si una cambia, cambian las dos.
 */
const fail = (code: string, field: string, day?: string) => ({ ok: false, problem: { code, field, ...(day ? { day } : {}) } });

describe("business-rules (spec 056)", () => {
  it("los valores son los de la spec y los de la API", () => {
    expect(MAX_SHIFTS_PER_DAY).toBe(6);
    expect(MINUTES_PER_DAY).toBe(1440);
    expect(TIME_STEP).toBe(5);
    expect([DURATION_MIN, DURATION_MAX, DURATION_STEP]).toEqual([5, 480, 5]);
    expect(PRICE_KINDS).toEqual(["none", "free", "amount"]);
    expect(AMOUNT_MAX_MINOR).toBe(10 ** 12);
    expect(CATEGORY_MAX).toBe(40);
    expect([NAME_MIN, NAME_MAX]).toEqual([1, 120]);
    expect(WEEK_DAYS).toEqual(DAYS);
  });

  it("las duraciones que ofrece la ficha son justo las que valen", () => {
    expect(DURATIONS.every(durationOk)).toBe(true);
    expect(DURATIONS).toHaveLength((DURATION_MAX - DURATION_MIN) / DURATION_STEP + 1);
  });

  describe("las horas", () => {
    it("en pasos de 5 minutos, con 24:00 solo de cierre", () => {
      expect(timeMinutes("00:00")).toEqual({ ok: true, value: 0 });
      expect(timeMinutes("09:05")).toEqual({ ok: true, value: 545 });
      expect(timeMinutes("23:55")).toEqual({ ok: true, value: 1435 });
      expect(timeMinutes("24:00", { closing: true })).toEqual({ ok: true, value: 1440 });
      expect(timeMinutes("24:00")).toEqual(fail("invalid_time", "open"));
    });

    it("fuera del paso es bad_step", () => {
      for (const raw of ["09:07", "12:01", "23:59"]) expect(timeMinutes(raw)).toEqual(fail("bad_step", "open"));
    });

    it("lo que no es HH:MM es invalid_time", () => {
      for (const raw of ["9:00", "25:00", "12:60", "ab:cd", "", "24:05"]) {
        expect(timeMinutes(raw, { closing: true })).toEqual(fail("invalid_time", "close"));
      }
    });

    it("onStep marca lo que hay que revisar (5.5)", () => {
      expect(onStep(540)).toBe(true);
      expect(onStep(541)).toBe(false);
    });
  });

  describe("los turnos", () => {
    it("un cierre igual o anterior a la apertura es del día siguiente", () => {
      expect(shiftMinutes("20:00", "02:00")).toEqual({ ok: true, value: [1200, 1560] });
      expect(shiftMinutes("09:00", "00:00")).toEqual({ ok: true, value: [540, 1440] });
      expect(shiftMinutes("00:00", "24:00")).toEqual({ ok: true, value: [0, 1440] });
      expect(shiftMinutes("00:00", "00:00")).toEqual({ ok: true, value: [0, 1440] });
      expect(shiftMinutes("09:00", "13:30")).toEqual({ ok: true, value: [540, 810] });
    });

    it("de 0 a 6 turnos al día", () => {
      expect(checkDay([])).toEqual({ ok: true, value: [] });
      const six = [8, 10, 12, 14, 16, 18].map((h) => ({ open: `${String(h).padStart(2, "0")}:00`, close: `${String(h).padStart(2, "0")}:30` }));
      const ok = checkDay(six);
      expect(ok.ok && ok.value.length).toBe(6);
      expect(checkDay([...six, { open: "21:00", close: "21:30" }], "mon")).toEqual(fail("too_many_shifts", "shifts", "mon"));
    });

    it("vuelven en orden", () => {
      expect(
        checkDay([
          { open: "16:00", close: "20:00" },
          { open: "09:00", close: "13:00" },
        ]),
      ).toEqual({
        ok: true,
        value: [
          [540, 780],
          [960, 1200],
        ],
      });
    });

    it("dos turnos del mismo día no se solapan; tocarse sí vale", () => {
      expect(
        checkDay(
          [
            { open: "09:00", close: "14:00" },
            { open: "13:00", close: "18:00" },
          ],
          "tue",
        ),
      ).toEqual(fail("overlap", "shifts", "tue"));
      expect(
        checkDay([
          { open: "09:00", close: "14:00" },
          { open: "14:00", close: "18:00" },
        ]).ok,
      ).toBe(true);
    });

    it("un paso mal dice su día", () => {
      expect(checkDay([{ open: "09:00", close: "13:03" }], "wed")).toEqual(fail("bad_step", "close", "wed"));
    });

    it("un nocturno no pisa el día siguiente, y el domingo sigue en el lunes", () => {
      expect(checkWeek({ fri: [{ open: "22:00", close: "03:00" }], sat: [{ open: "02:00", close: "08:00" }] })).toEqual(fail("overlap_next_day", "shifts", "fri"));
      expect(checkWeek({ sun: [{ open: "23:00", close: "01:00" }], mon: [{ open: "00:30", close: "09:00" }] })).toEqual(fail("overlap_next_day", "shifts", "sun"));
      const ok = checkWeek({ fri: [{ open: "22:00", close: "03:00" }], sat: [{ open: "03:00", close: "08:00" }] });
      expect(ok.ok).toBe(true);
      if (ok.ok) {
        expect(ok.value.fri).toEqual([[1320, 1620]]);
        expect(ok.value.sat).toEqual([[180, 480]]);
        expect(ok.value.mon).toEqual([]);
      }
    });

    it("una semana solo tiene sus siete días", () => {
      expect(checkWeek({ funday: [{ open: "09:00", close: "10:00" }] })).toEqual(fail("invalid_day", "days", "funday"));
    });
  });

  describe("los servicios", () => {
    it("duración de 5 a 480, en pasos de 5", () => {
      for (const m of [5, 30, 45, 475, 480]) {
        expect(durationOk(m)).toBe(true);
        expect(checkDuration(m)).toEqual({ ok: true, value: m });
      }
      for (const m of [0, 4, 7, 485, 500, -5, 12.5]) {
        expect(durationOk(m)).toBe(false);
        expect(checkDuration(m)).toEqual(fail("bad_duration", "duration_min"));
      }
    });

    it("el precio es sin precio, gratis o un importe; gratis no guarda importe", () => {
      expect(checkPrice("none", null)).toEqual({ ok: true, value: null });
      expect(checkPrice("free", null)).toEqual({ ok: true, value: null });
      expect(checkPrice("free", 500)).toEqual({ ok: true, value: null });
      expect(checkPrice("amount", 0)).toEqual({ ok: true, value: 0 });
      expect(checkPrice("amount", 1550)).toEqual({ ok: true, value: 1550 });
      expect(checkPrice("amount", 10 ** 12)).toEqual({ ok: true, value: 10 ** 12 });
    });

    it("un precio mal dice por qué", () => {
      expect(checkPrice("gift", null)).toEqual(fail("price_invalid", "price"));
      expect(checkPrice("amount", null)).toEqual(fail("price_amount_required", "price"));
      expect(checkPrice("amount", -1)).toEqual(fail("price_invalid", "price"));
      expect(checkPrice("amount", 1.5)).toEqual(fail("price_invalid", "price"));
      expect(checkPrice("amount", 10 ** 12 + 1)).toEqual(fail("amount_too_large", "price"));
    });

    it("la categoría admite hasta 40 caracteres, con los espacios colapsados", () => {
      expect(checkCategory(null)).toEqual({ ok: true, value: null });
      expect(checkCategory("   ")).toEqual({ ok: true, value: null });
      expect(checkCategory("  Corte   y  barba ")).toEqual({ ok: true, value: "Corte y barba" });
      expect(checkCategory("x".repeat(40))).toEqual({ ok: true, value: "x".repeat(40) });
      expect(checkCategory("x".repeat(41))).toEqual(fail("category_too_long", "category"));
    });

    it("el nombre, de 1 a 120 caracteres", () => {
      expect(checkName("  Corte   de pelo ")).toEqual({ ok: true, value: "Corte de pelo" });
      expect(checkName("x".repeat(120))).toEqual({ ok: true, value: "x".repeat(120) });
      expect(checkName("   ")).toEqual(fail("name_required", "name"));
      expect(checkName("x".repeat(121))).toEqual(fail("name_too_long", "name"));
    });
  });
});
