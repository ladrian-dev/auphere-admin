import type { Booking, TimeRange } from "@/lib/backend/reservas";

import { toMinutes } from "./dates";

/**
 * The time grid of Servicios (spec 043, T023): one column per professional on
 * a day, or per day for one professional on a week. Everything here is
 * minutes since local midnight, so it is plain arithmetic and testable.
 */

export type Span = { from: number; to: number };

/** Rows of the grid: 30 min each, as the design draws them (56 px per hour). */
export const GRID_STEP = 30;
const DEFAULT_BOUNDS: Span = { from: 9 * 60, to: 19 * 60 };

export function spansOf(ranges: readonly TimeRange[] | undefined): Span[] {
  return (ranges ?? [])
    .map((r) => ({ from: toMinutes(r.from), to: toMinutes(r.to) }))
    .filter((s) => s.to > s.from)
    .sort((a, b) => a.from - b.from);
}

/** A booking as minutes; one that runs past midnight is cut there. */
export function bookingSpan(b: Pick<Booking, "local">): Span {
  const from = toMinutes(b.local.start);
  const to = toMinutes(b.local.end);
  return { from, to: to > from ? to : 1440 };
}

/** Whole hours that contain every working range and every booking; 9–19 when there is nothing. */
export function gridBounds(spans: readonly Span[][], items: readonly Span[]): Span {
  const all = [...spans.flat(), ...items];
  if (all.length === 0) return DEFAULT_BOUNDS;
  const from = Math.floor(Math.min(...all.map((s) => s.from)) / 60) * 60;
  const to = Math.ceil(Math.max(...all.map((s) => s.to)) / 60) * 60;
  return { from, to: Math.max(to, from + 60) };
}

export function gridRows(bounds: Span, step = GRID_STEP): number[] {
  const out: number[] = [];
  for (let m = bounds.from; m < bounds.to; m += step) out.push(m);
  return out;
}

export type Gap = Span & { kind: "closed" | "pause" };

/**
 * What is not working time inside the grid: before the first range and after
 * the last it is «Cerrado»; between two ranges, «Pausa» (the lunch break of
 * spec §Clarifications). A day without ranges is closed from end to end.
 */
export function gapsOf(spans: readonly Span[], bounds: Span): Gap[] {
  if (spans.length === 0) return [{ ...bounds, kind: "closed" }];
  const out: Gap[] = [];
  const first = spans[0]!;
  const last = spans[spans.length - 1]!;
  if (first.from > bounds.from) out.push({ from: bounds.from, to: first.from, kind: "closed" });
  for (let i = 1; i < spans.length; i++) {
    const prev = spans[i - 1]!;
    const cur = spans[i]!;
    if (cur.from > prev.to) out.push({ from: prev.to, to: cur.from, kind: "pause" });
  }
  if (last.to < bounds.to) out.push({ from: last.to, to: bounds.to, kind: "closed" });
  return out;
}

export type Placed<T> = { item: T; lane: number; lanes: number };

/**
 * Overlapping bookings side by side (the design's «carriles»): a cluster is a
 * chain of bookings that overlap one another; inside it, each takes the first
 * lane that is free at its start, and all of them share the cluster's width.
 */
export function placeInLanes<T>(items: readonly T[], span: (item: T) => Span): Placed<T>[] {
  const sorted = [...items].sort((a, b) => span(a).from - span(b).from || span(b).to - span(a).to);
  const out: Placed<T>[] = [];
  let cluster: Placed<T>[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -1;
  const close = () => {
    for (const p of cluster) p.lanes = laneEnds.length;
    out.push(...cluster);
    cluster = [];
    laneEnds = [];
  };
  for (const item of sorted) {
    const s = span(item);
    if (cluster.length > 0 && s.from >= clusterEnd) close();
    let lane = laneEnds.findIndex((end) => end <= s.from);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(s.to);
    } else {
      laneEnds[lane] = s.to;
    }
    cluster.push({ item, lane, lanes: 0 });
    clusterEnd = Math.max(clusterEnd, s.to);
  }
  if (cluster.length > 0) close();
  return out;
}

/** A booking that still holds its time: everything except cancelled. */
export function holdsTime(b: Pick<Booking, "status">): boolean {
  return b.status !== "cancelled";
}

/** A booking that still may happen. */
export function isLive(b: Pick<Booking, "status">): boolean {
  return b.status === "pending" || b.status === "confirmed" || b.status === "arrived";
}

function overlaps(a: Span, b: Span): boolean {
  return a.from < b.to && b.from < a.to;
}

export type CellKind = "free" | "taken" | "off" | "past";

/**
 * One 30-min cell. Free = fully inside a working range, not under a booking,
 * not started yet. Past and closed cells do not answer (design §3.1).
 */
export function cellKind(
  start: number,
  ctx: { spans: readonly Span[]; busy: readonly Span[]; past: (start: number) => boolean; step?: number },
): CellKind {
  const cell = { from: start, to: start + (ctx.step ?? GRID_STEP) };
  if (!ctx.spans.some((s) => s.from <= cell.from && cell.to <= s.to)) return "off";
  if (ctx.past(start)) return "past";
  if (ctx.busy.some((b) => overlaps(b, cell))) return "taken";
  return "free";
}

/** «N reservas · X %»: booked minutes over working minutes, without what was cancelled. */
export function bookedPercent(spans: readonly Span[], bookings: readonly Pick<Booking, "local" | "status">[]): number {
  const open = spans.reduce((sum, s) => sum + (s.to - s.from), 0);
  if (open <= 0) return 0;
  const booked = bookings.filter(holdsTime).reduce((sum, b) => {
    const s = bookingSpan(b);
    return sum + (s.to - s.from);
  }, 0);
  return Math.min(100, Math.round((booked / open) * 100));
}

export type BookingTone = "pending" | "confirmed" | "inCourse" | "arrived" | "done" | "noshow" | "cancelled" | "clash";

/** How a booking block looks: its status, plus «en curso» (today, started, not over) and a P3 clash. */
export function bookingTone(b: Pick<Booking, "status" | "local" | "clash">, today: string, nowMinutes: number): BookingTone {
  if (b.status === "cancelled") return "cancelled";
  if (b.status === "noshow") return "noshow";
  if (b.status === "done") return "done";
  if (b.clash && (b.status === "pending" || b.status === "confirmed")) return "clash";
  const span = bookingSpan(b);
  if (b.local.date === today && span.from <= nowMinutes && nowMinutes < span.to && isLive(b)) return "inCourse";
  if (b.status === "arrived") return "arrived";
  return b.status === "pending" ? "pending" : "confirmed";
}
