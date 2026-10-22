import { describe, expect, it } from "vitest";

import type { Booking } from "@/lib/backend/reservas";

import { bookedPercent, bookingSpan, bookingTone, cellKind, gapsOf, gridBounds, gridRows, placeInLanes, spansOf } from "../day-grid";
import {
  currentSlotTime,
  groupByArrival,
  heatLevel,
  hourState,
  mapColumns,
  nextSlotTime,
  peakSlot,
  scheduleTimes,
  seatsStep,
  slotAt,
} from "../occupancy";
import { NOW_MIN, TODAY, booking, capacityBooking, occupancyDay } from "./fixtures";

const at = (start: string, end: string, o: Partial<Booking> = {}) => booking({ local: { date: TODAY, start, end }, ...o });

/** Spec 043 (T023): the agenda by professional — pauses, closed hours, lanes, free cells. */
describe("the day grid of Servicios", () => {
  const lucia = spansOf([
    { from: "15:00", to: "19:00" },
    { from: "09:00", to: "14:00" },
  ]);

  it("reads the ranges in order and paints the gap between them as «Pausa»", () => {
    expect(lucia).toEqual([
      { from: 540, to: 840 },
      { from: 900, to: 1140 },
    ]);
    const bounds = gridBounds([lucia], []);
    expect(bounds).toEqual({ from: 540, to: 1140 });
    expect(gapsOf(lucia, { from: 480, to: 1200 })).toEqual([
      { from: 480, to: 540, kind: "closed" },
      { from: 840, to: 900, kind: "pause" },
      { from: 1140, to: 1200, kind: "closed" },
    ]);
    expect(gapsOf([], bounds)).toEqual([{ ...bounds, kind: "closed" }]);
  });

  it("the grid grows to whole hours to fit a booking outside the hours", () => {
    expect(gridBounds([lucia], [{ from: 1170, to: 1215 }])).toEqual({ from: 540, to: 1260 });
    expect(gridBounds([], [])).toEqual({ from: 540, to: 1140 });
    expect(gridRows({ from: 540, to: 660 })).toEqual([540, 570, 600, 630]);
  });

  it("overlapping bookings share the width in lanes; the next cluster starts over", () => {
    const a = at("10:00", "11:00");
    const b = at("10:30", "11:15");
    const c = at("11:00", "11:30");
    const d = at("12:00", "12:30");
    const placed = placeInLanes([d, c, b, a], bookingSpan);
    const of = (x: Booking) => placed.find((p) => p.item === x)!;
    expect(of(a)).toMatchObject({ lane: 0, lanes: 2 });
    expect(of(b)).toMatchObject({ lane: 1, lanes: 2 });
    expect(of(c)).toMatchObject({ lane: 0, lanes: 2 });
    expect(of(d)).toMatchObject({ lane: 0, lanes: 1 });
  });

  it("a cell is free only inside the hours, not started, and not under a booking", () => {
    const busy = [bookingSpan(at("16:30", "17:15"))];
    const past = (m: number) => m < NOW_MIN;
    expect(cellKind(13 * 60 + 30, { spans: lucia, busy, past: () => false })).toBe("free");
    expect(cellKind(14 * 60, { spans: lucia, busy, past: () => false })).toBe("off");
    expect(cellKind(16 * 60, { spans: lucia, busy, past })).toBe("past");
    expect(cellKind(17 * 60, { spans: lucia, busy, past })).toBe("taken");
    expect(cellKind(17 * 60 + 30, { spans: lucia, busy, past })).toBe("free");
  });

  it("«N reservas · X %» counts booked minutes over working minutes, cancelled ones out", () => {
    const list = [at("09:00", "10:30"), at("11:00", "12:00", { status: "cancelled" })];
    expect(bookedPercent(lucia, list)).toBe(17); // 90 of 540
    expect(bookedPercent([], list)).toBe(0);
  });

  it("a booking looks like its status, «en curso» while it happens, and a clash when Google says so", () => {
    expect(bookingTone(at("16:30", "17:15"), TODAY, NOW_MIN)).toBe("inCourse");
    expect(bookingTone(at("18:00", "18:45", { status: "pending" }), TODAY, NOW_MIN)).toBe("pending");
    expect(bookingTone(at("09:00", "09:45", { status: "done" }), TODAY, NOW_MIN)).toBe("done");
    expect(bookingTone(at("09:00", "09:45", { status: "noshow" }), TODAY, NOW_MIN)).toBe("noshow");
    expect(
      bookingTone(at("18:00", "18:45", { clash: { source: "google", local: { start: "18:00", end: "19:00" } } }), TODAY, NOW_MIN),
    ).toBe("clash");
  });
});

/** Spec 043 (T024): the occupancy map and the hour panel of Aforo. */
describe("occupancy of Aforo", () => {
  it("five levels from people inside, «full» when nothing is left to book", () => {
    expect(heatLevel(10, 64, 6)).toBe("l1");
    expect(heatLevel(30, 64, 6)).toBe("l2");
    expect(heatLevel(40, 64, 6)).toBe("l3");
    expect(heatLevel(56, 64, 6)).toBe("l4");
    expect(heatLevel(58, 64, 6)).toBe("full");
    expect(heatLevel(0, 0, 0)).toBe("full");
  });

  it("arrival times of shifts and of slots, the last one included", () => {
    expect(
      scheduleTimes({ model: "shifts", step_minutes: 30, shifts: [{ name: "Comida", from: "13:00", to: "14:00" }, { name: "Cena", from: "20:00", to: "20:30" }] }),
    ).toEqual([
      { time: "13:00", shift: "Comida" },
      { time: "13:30", shift: "Comida" },
      { time: "14:00", shift: "Comida" },
      { time: "20:00", shift: "Cena" },
      { time: "20:30", shift: "Cena" },
    ]);
    expect(scheduleTimes({ model: "slots", step_minutes: 120, from: "10:00", to: "16:00" }).map((s) => s.time)).toEqual([
      "10:00",
      "12:00",
      "14:00",
      "16:00",
    ]);
    expect(scheduleTimes(null)).toEqual([]);
  });

  it("the map's columns are the union of the days' slots, under their shift", () => {
    const a = occupancyDay("2026-10-22");
    const b = occupancyDay("2026-10-26", { closed: true, slots: [] });
    const cols = mapColumns([a, b]);
    expect(cols.map((c) => c.shift)).toEqual(["Comida", "Cena"]);
    expect(cols[0]!.times).toEqual(["13:00", "13:30", "14:00", "14:30", "15:00"]);
    expect(mapColumns([], [{ time: "12:00", shift: null }])).toEqual([{ shift: null, times: ["12:00"] }]);
  });

  it("the hour panel says closed, blocked, started, full, or how many are left", () => {
    const day = occupancyDay(TODAY);
    const s = slotAt(day, "20:30")!;
    expect(hourState(day, { ...s, present: 40 }, 64, 6)).toEqual({ kind: "open", left: 18 });
    expect(hourState(day, { ...s, present: 58 }, 64, 6)).toEqual({ kind: "full" });
    expect(hourState(day, { ...s, past: true }, 64, 6)).toEqual({ kind: "past" });
    expect(hourState(day, { ...s, past: true, blocked: { id: "b", label: "Evento privado" } }, 64, 6)).toEqual({
      kind: "blocked",
      label: "Evento privado",
      blockId: "b",
    });
    expect(hourState({ ...day, closed: true }, s, 64, 6)).toEqual({ kind: "closed" });
    expect(hourState(day, undefined, 64, 6)).toEqual({ kind: "closed" });
  });

  it("groups a day's bookings by arrival, people counted without cancelled or no-shows", () => {
    const groups = groupByArrival([
      capacityBooking({ local: { date: TODAY, start: "21:00", end: "22:30" }, party_size: 2 }),
      capacityBooking({ party_size: 4 }),
      capacityBooking({ party_size: 6, status: "noshow" }),
      capacityBooking({ party_size: 3, status: "cancelled" }),
    ]);
    expect(groups.map((g) => [g.time, g.bookings.length, g.people])).toEqual([
      ["20:30", 2, 4],
      ["21:00", 1, 2],
    ]);
  });

  it("the slot in course and the next one, for «Llega alguien sin reserva»", () => {
    const times = ["13:00", "13:30", "14:00", "20:00"];
    expect(currentSlotTime(times, 13 * 60 + 40, 30)).toBe("13:30");
    expect(currentSlotTime(times, 16 * 60, 30)).toBeNull();
    expect(nextSlotTime(times, 16 * 60)).toBe("20:00");
    expect(nextSlotTime(times, 21 * 60)).toBeNull();
  });

  it("peak and −/+ steps", () => {
    const day = occupancyDay(TODAY);
    day.slots[6]!.present = 58;
    expect(peakSlot(day)?.time).toBe("20:30");
    expect(peakSlot(undefined)).toBeNull();
    expect(seatsStep(64)).toBe(3);
    expect(seatsStep(14)).toBe(1);
  });
});
