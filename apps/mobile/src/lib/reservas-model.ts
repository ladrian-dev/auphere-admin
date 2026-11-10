import type { Reservation, ResConfig } from "@/api/reservas";

/**
 * Reservas' pure rules (spec 044, data-model.md): what the phone works out by
 * itself about a day, always in the business's wall time — a date
 * (`YYYY-MM-DD`) and minutes since midnight — never in the phone's zone
 * (research D3). Tested without rendering.
 */
export type LocalDate = string;
export type Minutes = number;
export type WallTime = { date: LocalDate; minutes: Minutes };

// ── clock ─────────────────────────────────────────────────────────────

export function parseHHMM(s: string): Minutes {
  const [h, m] = s.split(":");
  return Number(h) * 60 + Number(m ?? 0);
}

export function hhmm(m: Minutes): string {
  const h = Math.floor(m / 60) % 24;
  const mm = Math.round(m % 60);
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function utc(d: LocalDate): Date {
  return new Date(`${d}T12:00:00Z`);
}

function iso(date: Date): LocalDate {
  return date.toISOString().slice(0, 10);
}

export function addDays(d: LocalDate, n: number): LocalDate {
  const x = utc(d);
  x.setUTCDate(x.getUTCDate() + n);
  return iso(x);
}

/** 1 Monday … 7 Sunday, as the business hours count them. */
export function weekday(d: LocalDate): 1 | 2 | 3 | 4 | 5 | 6 | 7 {
  const js = utc(d).getUTCDay();
  return (js === 0 ? 7 : js) as 1 | 2 | 3 | 4 | 5 | 6 | 7;
}

export function weekStart(d: LocalDate): LocalDate {
  return addDays(d, 1 - weekday(d));
}

export function monthStart(d: LocalDate): LocalDate {
  return `${d.slice(0, 7)}-01`;
}

export function monthEnd(d: LocalDate): LocalDate {
  const x = utc(monthStart(d));
  x.setUTCMonth(x.getUTCMonth() + 1);
  x.setUTCDate(0);
  return iso(x);
}

export function addMonths(d: LocalDate, n: number): LocalDate {
  const x = utc(monthStart(d));
  x.setUTCMonth(x.getUTCMonth() + n);
  return iso(x);
}

/** The month as weeks from Monday; days of the months around it are `null`. */
export function monthGrid(d: LocalDate): (LocalDate | null)[][] {
  const first = monthStart(d);
  const last = monthEnd(d);
  const weeks: (LocalDate | null)[][] = [];
  let cursor = weekStart(first);
  while (cursor <= last) {
    const week: (LocalDate | null)[] = [];
    for (let i = 0; i < 7; i++) {
      const day = addDays(cursor, i);
      week.push(day >= first && day <= last ? day : null);
    }
    weeks.push(week);
    cursor = addDays(cursor, 7);
  }
  return weeks;
}

/** A moment as the wall clock of a time zone reads it. Falls back to the phone's own zone if the runtime has no zone data. */
export function wallClock(tz: string, at: Date = new Date()): WallTime {
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(at);
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "00";
    return { date: `${get("year")}-${get("month")}-${get("day")}`, minutes: Number(get("hour")) * 60 + Number(get("minute")) };
  } catch {
    const p = (n: number) => String(n).padStart(2, "0");
    return { date: `${at.getFullYear()}-${p(at.getMonth() + 1)}-${p(at.getDate())}`, minutes: at.getHours() * 60 + at.getMinutes() };
  }
}

/** «Now» as the server said it, in the business's wall time, and when the phone read it. */
export type BizNow = WallTime & { readAt: number };

export function nowFrom(serverIso: string, readAt: number): BizNow {
  // The API writes it with the business's own offset: its date and time ARE the wall clock.
  const date = serverIso.slice(0, 10);
  const minutes = parseHHMM(serverIso.slice(11, 16));
  return { date, minutes, readAt };
}

/** The server's «now», moved on by what the phone's clock says has passed since. */
export function sinceMinutes(now: BizNow, at: number = Date.now()): WallTime {
  const total = now.minutes + Math.floor((at - now.readAt) / 60_000);
  const days = Math.floor(total / 1440);
  return { date: addDays(now.date, days), minutes: total - days * 1440 };
}

// ── a day ─────────────────────────────────────────────────────────────

export function isClosed(config: ResConfig, date: LocalDate): boolean {
  const wd = weekday(date);
  if (!config.hours.some((h) => h.weekday === wd)) return true;
  if (config.mode === "capacity" && config.capacity) return slotsOfDay(config, date).length === 0;
  return false;
}

export function openSpan(config: ResConfig, date: LocalDate): { open: Minutes; close: Minutes } | null {
  const spans = config.hours.filter((h) => h.weekday === weekday(date));
  if (spans.length === 0) return null;
  return { open: Math.min(...spans.map((s) => s.open)), close: Math.max(...spans.map((s) => s.close)) };
}

/** Aforo: the arrival times of a day, shift by shift, without the shifts closed that weekday. */
export function slotsOfDay(config: ResConfig, date: LocalDate): { shift: string; time: Minutes }[] {
  const cap = config.capacity;
  if (!cap) return [];
  const wd = weekday(date);
  if (!config.hours.some((h) => h.weekday === wd)) return [];
  const out: { shift: string; time: Minutes }[] = [];
  for (const s of cap.shifts) {
    if (cap.closed.some((c) => c.weekday === wd && (c.shift === null || c.shift === s.name))) continue;
    for (let t = s.from; t <= s.to; t += s.everyMin) out.push({ shift: s.name, time: t });
  }
  return out;
}

/** The slot under way: the last arrival time that has started, within its shift's stay. */
export function currentSlot(config: ResConfig, date: LocalDate, minutes: Minutes): Minutes | null {
  const cap = config.capacity;
  if (!cap) return null;
  const started = slotsOfDay(config, date).filter((s) => s.time <= minutes);
  const last = started.at(-1);
  if (!last) return null;
  const shift = cap.shifts.find((s) => s.name === last.shift);
  const end = (shift?.to ?? last.time) + (shift?.everyMin ?? 30);
  return minutes < end ? last.time : null;
}

const OPEN: ReadonlySet<Reservation["state"]> = new Set(["pending", "confirmed", "arrived"]);

export function isOpen(r: Pick<Reservation, "state">): boolean {
  return OPEN.has(r.state);
}

export function isPast(r: Pick<Reservation, "date" | "end">, now: WallTime): boolean {
  return r.date < now.date || (r.date === now.date && r.end <= now.minutes);
}

export function daySummary(items: readonly Pick<Reservation, "state">[]): { total: number; unconfirmed: number } {
  const live = items.filter((r) => r.state !== "cancelled");
  return { total: live.length, unconfirmed: live.filter((r) => r.state === "pending").length };
}

/** People inside at a time: the ones whose stay covers it, never the cancelled or the no-shows. */
export function insideAt(items: readonly Reservation[], date: LocalDate, t: Minutes, stayMin: number): number {
  return items
    .filter((r) => r.date === date && r.state !== "cancelled" && r.state !== "noshow" && r.state !== "done")
    .filter((r) => r.start <= t && t < r.start + stayMin)
    .reduce((sum, r) => sum + (r.partySize ?? 0), 0);
}

/** «Llega tarde · N min»: still expected, 15 minutes or more past its time, and its stay not over. */
export function lateBy(r: Reservation, now: WallTime, stayMin: number): number | null {
  if (r.date !== now.date || (r.state !== "pending" && r.state !== "confirmed")) return null;
  const late = now.minutes - r.start;
  return late >= 15 && now.minutes < r.start + stayMin ? late : null;
}

export function arrivingNextHour(items: readonly Reservation[], now: WallTime): number {
  return items
    .filter((r) => r.date === now.date && (r.state === "pending" || r.state === "confirmed"))
    .filter((r) => r.start >= now.minutes && r.start < now.minutes + 60)
    .reduce((sum, r) => sum + (r.partySize ?? 0), 0);
}

/** The next open ones of the day, from now on. */
export function upcoming(items: readonly Reservation[], now: WallTime, n = 3): Reservation[] {
  return items
    .filter((r) => r.date === now.date && isOpen(r) && r.state !== "arrived" && r.start >= now.minutes)
    .sort((a, b) => a.start - b.start)
    .slice(0, n);
}

/** Occupancy in the steps the legend uses: < 35 %, 35–60, 60–85, ≥ 85, and full. */
export function occupancyLevel(inside: number, capacity: number): 0 | 1 | 2 | 3 | "full" {
  if (capacity <= 0 || inside >= capacity) return "full";
  const pct = inside / capacity;
  return pct < 0.35 ? 0 : pct < 0.6 ? 1 : pct < 0.85 ? 2 : 3;
}

// ── Consumo (R13.1) ───────────────────────────────────────────────────

/** The day the balance runs out at the 7-day pace: today plus the whole days left. */
export function runsOutOn(daysLeft: number | null | undefined, today: LocalDate): LocalDate | null {
  if (daysLeft == null || !Number.isFinite(daysLeft) || daysLeft < 0) return null;
  return addDays(today, Math.floor(daysLeft));
}
