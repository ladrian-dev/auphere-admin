import { WEEKDAYS, type Weekday } from "@/lib/backend/reservas";

/**
 * Days and hours of Reservas, as the API speaks them: a day is `YYYY-MM-DD`
 * and an hour `HH:MM`, both **local to the business** (spec 043, «Fechas y
 * horas»). The arithmetic runs on UTC midnights so that no browser time zone
 * — nor a daylight-saving jump — ever moves a day; the business's zone is
 * only used once, to know what «today» and «now» are there.
 */

export type Period = "day" | "week" | "month";
export type Locale = "es" | "en";

const DAY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

function toUtc(day: string): Date {
  const m = DAY_RE.exec(day);
  if (!m) throw new Error(`not a day: ${day}`);
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

function fromUtc(dt: Date): string {
  return dt.toISOString().slice(0, 10);
}

/** A real calendar day (`2026-02-30` is not). */
export function isDay(value: unknown): value is string {
  if (typeof value !== "string" || !DAY_RE.test(value)) return false;
  return fromUtc(toUtc(value)) === value;
}

export function isTime(value: unknown): value is string {
  return typeof value === "string" && TIME_RE.test(value);
}

export function addDays(day: string, n: number): string {
  const dt = toUtc(day);
  dt.setUTCDate(dt.getUTCDate() + n);
  return fromUtc(dt);
}

/** Whole days from `a` to `b` (`b − a`). */
export function diffDays(a: string, b: string): number {
  return Math.round((toUtc(b).getTime() - toUtc(a).getTime()) / 86_400_000);
}

/** 0 = Monday … 6 = Sunday (the week starts on Monday in Chile and in Spain). */
export function weekdayIndex(day: string): number {
  return (toUtc(day).getUTCDay() + 6) % 7;
}

export function weekdayOf(day: string): Weekday {
  return WEEKDAYS[weekdayIndex(day)]!;
}

export function startOfWeek(day: string): string {
  return addDays(day, -weekdayIndex(day));
}

export function startOfMonth(day: string): string {
  return `${day.slice(0, 8)}01`;
}

export function endOfMonth(day: string): string {
  const dt = toUtc(startOfMonth(day));
  dt.setUTCMonth(dt.getUTCMonth() + 1);
  dt.setUTCDate(0);
  return fromUtc(dt);
}

/** Every day from `from` to `to`, both included. */
export function daysBetween(from: string, to: string): string[] {
  const out: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) out.push(d);
  return out;
}

export type DayRange = { from: string; to: string };

/** The days a period covers around `day`: the day, its Monday-to-Sunday week, or its month. */
export function periodRange(period: Period, day: string): DayRange {
  if (period === "day") return { from: day, to: day };
  if (period === "week") {
    const from = startOfWeek(day);
    return { from, to: addDays(from, 6) };
  }
  return { from: startOfMonth(day), to: endOfMonth(day) };
}

/** ‹ and ›: one day, one week, or one month (landing on its first day). */
export function shiftPeriod(period: Period, day: string, dir: 1 | -1): string {
  if (period === "day") return addDays(day, dir);
  if (period === "week") return addDays(day, 7 * dir);
  const dt = toUtc(startOfMonth(day));
  dt.setUTCMonth(dt.getUTCMonth() + dir);
  return fromUtc(dt);
}

/** The month as Monday-first weeks (5 or 6), with the days of the neighbouring months that fill them. */
export function monthWeeks(day: string): string[][] {
  const first = startOfWeek(startOfMonth(day));
  const last = addDays(startOfWeek(endOfMonth(day)), 6);
  const days = daysBetween(first, last);
  const weeks: string[][] = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return weeks;
}

export function inRange(day: string, range: DayRange): boolean {
  return day >= range.from && day <= range.to;
}

// ── hours ────────────────────────────────────────────────────────────────

export function toMinutes(time: string): number {
  const [h, m] = time.split(":");
  return Number(h) * 60 + Number(m);
}

export function fromMinutes(minutes: number): string {
  const m = ((minutes % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** «45 min», «1 h», «1 h 30 min» — the same in Spanish and English. */
export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

/** What «today» and «now» are in the business's time zone. */
export function localClock(now: Date, timeZone: string): { date: string; minutes: number } {
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-GB", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(now);
  } catch {
    // An unknown zone would take the whole screen down; UTC is wrong but honest.
    return localClock(now, "UTC");
  }
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "00";
  const hour = Number(get("hour")) % 24;
  return { date: `${get("year")}-${get("month")}-${get("day")}`, minutes: hour * 60 + Number(get("minute")) };
}

// ── words ────────────────────────────────────────────────────────────────

export function capitalize(text: string): string {
  return text ? text.charAt(0).toLocaleUpperCase() + text.slice(1) : text;
}

function fmt(locale: Locale, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" });
}

/** «martes, 6 de octubre» · «Tuesday, October 6». */
export function dayLabel(day: string, locale: Locale): string {
  return fmt(locale, { weekday: "long", day: "numeric", month: "long" }).format(toUtc(day));
}

/** «Mié 7» · «Wed 7» (Intl puts English as «7 Wed», so it is composed by hand). */
export function shortDay(day: string, locale: Locale): string {
  return `${weekdayShort(day, locale)} ${Number(day.slice(8))}`;
}

/** «jueves 29» · «Thursday 29» — a day this month, inside a sentence. */
export function weekdayDay(day: string, locale: Locale): string {
  return `${fmt(locale, { weekday: "long" }).format(toUtc(day))} ${Number(day.slice(8))}`;
}

/** «Mié» · «Wed». */
export function weekdayShort(day: string, locale: Locale): string {
  return capitalize(fmt(locale, { weekday: "short" }).format(toUtc(day)).replace(".", ""));
}

/** «12 oct» · «Oct 12». */
export function shortDate(day: string, locale: Locale): string {
  return fmt(locale, { day: "numeric", month: "short" }).format(toUtc(day)).replace(".", "");
}

/** «Octubre de 2026» · «October 2026». */
export function monthLabel(day: string, locale: Locale): string {
  return capitalize(fmt(locale, { month: "long", year: "numeric" }).format(toUtc(day)));
}

/** The label next to ‹ ›: the day, the week («5 – 11 de octubre») or the month. */
export function periodLabel(period: Period, day: string, locale: Locale): string {
  if (period === "day") return capitalize(dayLabel(day, locale));
  if (period === "month") return monthLabel(day, locale);
  const { from, to } = periodRange("week", day);
  return fmt(locale, { day: "numeric", month: "long" }).formatRange(toUtc(from), toUtc(to));
}

export type RelativeWords = { today: string; tomorrow: string; yesterday: string };

/** «Hoy», «Mañana», «Ayer», or «Jue 8». */
export function relativeDay(day: string, today: string, locale: Locale, words: RelativeWords): string {
  const d = diffDays(today, day);
  if (d === 0) return words.today;
  if (d === 1) return words.tomorrow;
  if (d === -1) return words.yesterday;
  return shortDay(day, locale);
}

/** An instant (ISO, UTC) as a local day and hour of the business. */
export function instantLocal(iso: string, timeZone: string): { date: string; time: string } {
  const clock = localClock(new Date(iso), timeZone);
  return { date: clock.date, time: fromMinutes(clock.minutes) };
}

/**
 * The next `count` days the business opens, from `from` on (the day chips of
 * «Nueva reserva»: 12 in Servicios, 10 in Aforo). `include` is kept in its
 * place even if it falls further: a prefilled day is never dropped.
 */
export function openDays(from: string, count: number, isOpen: (day: string) => boolean, include?: string | null, maxScan = 120): string[] {
  const out: string[] = [];
  for (let i = 0; i < maxScan && out.length < count; i++) {
    const d = addDays(from, i);
    if (isOpen(d)) out.push(d);
  }
  if (include && include >= from && !out.includes(include)) out.push(include);
  return out.sort();
}
