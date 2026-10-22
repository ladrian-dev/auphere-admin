import type { Booking, CapacitySchedule, OccupancyDay, OccupancySlot } from "@/lib/backend/reservas";

import { fromMinutes, toMinutes } from "./dates";

/**
 * Aforo (spec 043, T024): people per hour, no tables. The map's colour, the
 * columns of the map, the hour panel's sentence and the list's groups come
 * from here.
 */

export type HeatLevel = "l1" | "l2" | "l3" | "l4" | "full";

/**
 * The five levels of the map (design: <35 %, 35–60 %, 60–85 %, >85 %, full).
 * «Full» is when nothing is left **to book** — seats minus the held seats
 * minus who is inside — which is when the agent stops offering the hour.
 */
export function heatLevel(present: number, seats: number, hold: number): HeatLevel {
  if (seats <= 0 || seats - hold - present <= 0) return "full";
  const pct = (present / seats) * 100;
  if (pct < 35) return "l1";
  if (pct < 60) return "l2";
  if (pct < 85) return "l3";
  return "l4";
}

export type ScheduleSlot = { time: string; shift: string | null };

/** Arrival times of the schedule: every `step` from each shift's start to its end, the last one included. */
export function scheduleTimes(schedule: CapacitySchedule | null | undefined): ScheduleSlot[] {
  if (!schedule || schedule.step_minutes <= 0) return [];
  const ranges =
    schedule.model === "shifts"
      ? schedule.shifts.map((s) => ({ shift: s.name as string | null, from: s.from, to: s.to }))
      : [{ shift: null, from: schedule.from, to: schedule.to }];
  const out: ScheduleSlot[] = [];
  for (const r of ranges) {
    for (let m = toMinutes(r.from); m <= toMinutes(r.to); m += schedule.step_minutes) {
      out.push({ time: fromMinutes(m), shift: r.shift });
    }
  }
  return out.sort((a, b) => a.time.localeCompare(b.time));
}

export type ColumnGroup = { shift: string | null; times: string[] };

/**
 * The map's columns: every arrival time any day of the period has (a day may
 * differ from another), in order, grouped under its shift's header
 * («Comida | Cena»). Without occupancy, the schedule decides.
 */
export function mapColumns(days: readonly OccupancyDay[], fallback: readonly ScheduleSlot[] = []): ColumnGroup[] {
  const shiftOf = new Map<string, string | null>();
  for (const d of days) for (const s of d.slots) if (!shiftOf.has(s.time)) shiftOf.set(s.time, s.shift);
  if (shiftOf.size === 0) for (const s of fallback) shiftOf.set(s.time, s.shift);
  const times = [...shiftOf.keys()].sort();
  const groups: ColumnGroup[] = [];
  for (const time of times) {
    const shift = shiftOf.get(time) ?? null;
    const last = groups[groups.length - 1];
    if (last && last.shift === shift) last.times.push(time);
    else groups.push({ shift, times: [time] });
  }
  return groups;
}

export function slotAt(day: OccupancyDay | undefined, time: string): OccupancySlot | undefined {
  return day?.slots.find((s) => s.time === time);
}

export type HourState =
  | { kind: "closed" }
  | { kind: "blocked"; label: string; blockId: string }
  | { kind: "past" }
  | { kind: "full" }
  | { kind: "open"; left: number };

/**
 * The sentence of the hour panel: closed, blocked (with its reason), already
 * started, full for bookings, or how many are left to book (held seats
 * aside). A blocked hour says so even when it is past: the block is the news.
 */
export function hourState(day: OccupancyDay | undefined, slot: OccupancySlot | undefined, seats: number, hold: number): HourState {
  if (!day || day.closed || !slot) return { kind: "closed" };
  if (slot.blocked) return { kind: "blocked", label: slot.blocked.label, blockId: slot.blocked.id };
  if (slot.past) return { kind: "past" };
  const left = seats - hold - slot.present;
  return left <= 0 ? { kind: "full" } : { kind: "open", left };
}

/** People a booking still puts in the room: not cancelled, not a no-show. */
export function counts(b: Pick<Booking, "status">): boolean {
  return b.status !== "cancelled" && b.status !== "noshow";
}

export type ArrivalGroup = { time: string; bookings: Booking[]; people: number };

/** Bookings of a day, by arrival time, with the people of each hour (cancelled ones stay out). */
export function groupByArrival(bookings: readonly Booking[]): ArrivalGroup[] {
  const byTime = new Map<string, Booking[]>();
  for (const b of bookings) {
    if (b.status === "cancelled") continue;
    const list = byTime.get(b.local.start) ?? [];
    list.push(b);
    byTime.set(b.local.start, list);
  }
  return [...byTime.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, list]) => ({ time, bookings: list, people: list.filter(counts).reduce((n, b) => n + b.party_size, 0) }));
}

/** The arrival slot in course at `nowMinutes`: the last one that started less than a step ago. */
export function currentSlotTime(times: readonly string[], nowMinutes: number, step: number): string | null {
  let current: string | null = null;
  for (const t of times) {
    const m = toMinutes(t);
    if (m <= nowMinutes && nowMinutes < m + step) current = t;
  }
  return current;
}

/** The next arrival slot after `nowMinutes`, or `null` when the day's service is over. */
export function nextSlotTime(times: readonly string[], nowMinutes: number): string | null {
  return [...times].sort().find((t) => toMinutes(t) > nowMinutes) ?? null;
}

/** The busiest slot of a day: «Pico 21:00 · 58 de 64». */
export function peakSlot(day: OccupancyDay | undefined): OccupancySlot | null {
  if (!day || day.slots.length === 0) return null;
  return day.slots.reduce((best, s) => (s.present > best.present ? s : best));
}

/** −/+ steps for the seats: about a twentieth of them, never less than one. */
export function seatsStep(seats: number): number {
  return Math.max(1, Math.round(seats / 20));
}
