import type { Reservation } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, hhmm, type LocalDate } from "@/lib/reservas-model";

/**
 * How Reservas writes dates, times, lengths and prices (spec 044). Dates are
 * the business's wall dates, read at noon UTC so no zone moves them a day.
 */
const at = (d: LocalDate) => new Date(`${d}T12:00:00Z`);
const cap = (s: string) => (s ? s[0]!.toLocaleUpperCase() + s.slice(1) : s);

/** «Miércoles, 22 de octubre». */
export function dayTitle(d: LocalDate, locale: Locale): string {
  return cap(at(d).toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }));
}

/** «mié 22» / «Wed 22». */
export function dayShort(d: LocalDate, locale: Locale): string {
  return at(d).toLocaleDateString(locale, { weekday: "short", day: "numeric", timeZone: "UTC" }).replace(".", "");
}

/** «mié». */
export function weekdayShort(d: LocalDate, locale: Locale): string {
  return at(d).toLocaleDateString(locale, { weekday: "short", timeZone: "UTC" }).replace(".", "");
}

export function dayNumber(d: LocalDate): string {
  return String(Number(d.slice(8, 10)));
}

/** «Octubre de 2026». */
export function monthTitle(d: LocalDate, locale: Locale): string {
  return cap(at(d).toLocaleDateString(locale, { month: "long", year: "numeric", timeZone: "UTC" }));
}

/** «19 – 25 de octubre» (the month once when both ends share it). */
export function weekRange(from: LocalDate, locale: Locale, t: T): string {
  const to = addDays(from, 6);
  const sameMonth = from.slice(0, 7) === to.slice(0, 7);
  const a = at(from).toLocaleDateString(locale, sameMonth ? { day: "numeric", timeZone: "UTC" } : { day: "numeric", month: "short", timeZone: "UTC" });
  const b = at(to).toLocaleDateString(locale, { day: "numeric", month: sameMonth ? "long" : "short", timeZone: "UTC" });
  return t("reservas.week.range", { from: a.replace(".", ""), to: b.replace(".", "") });
}

/** «Hoy», «Mañana» or «jue 24», for chips and summaries. */
export function relativeDay(d: LocalDate, today: LocalDate, locale: Locale, t: T): string {
  if (d === today) return t("reservas.today");
  if (d === addDays(today, 1)) return t("reservas.new.tomorrow");
  return cap(dayShort(d, locale));
}

export function duration(min: number, t: T): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return t("reservas.duration.min", { min: m });
  return m === 0 ? t("reservas.duration.h", { h }) : t("reservas.duration.hm", { h, min: m });
}

/** «1 h 30» where a column is narrow (a row's time); under an hour it is the same «45 min». */
export function durationShort(min: number, t: T): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h === 0 || m === 0 ? duration(min, t) : t("reservas.duration.hmShort", { h, min: m });
}

/** Prices of the business, in its own currency (CLP has no cents). */
export function price(amount: number, currency: string, locale: Locale): string {
  try {
    return new Intl.NumberFormat(locale === "es" ? "es-CL" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

export function party(n: number, unit: string, t: T): string {
  return t("reservas.party", { n, unit });
}

export function when(r: Pick<Reservation, "date" | "start" | "end">, today: LocalDate, locale: Locale, t: T): string {
  const from = hhmm(r.start);
  const to = hhmm(r.end);
  if (r.date === today) return t("reservas.when.today", { from, to });
  if (r.date === addDays(today, 1)) return t("reservas.when.tomorrow", { from, to });
  return t("reservas.when.other", { day: dayTitle(r.date, locale), from, to });
}

export function firstName(name: string): string {
  return name.split(" ")[0] ?? name;
}

/**
 * The customer's name, or «Sin nombre» for a walk-in who gave none (043 §4: the
 * API keeps `null`). Not «Sin reserva»: that is already the walk-in's pill.
 */
export function nameOf(r: Pick<Reservation, "customer">, t: T): string {
  return r.customer.name || t("reservas.noName");
}

/** A reservation said in one sentence for the screen reader, the same in the list and in the grid. */
export function spoken(r: Reservation, state: string, t: T, unit: string): string {
  const what = r.service && r.pro ? t("reservas.service.with", { service: r.service.name, pro: r.pro.name }) : r.partySize != null ? party(r.partySize, unit, t) : "";
  return [hhmm(r.start), nameOf(r, t), what, state].filter(Boolean).join(", ");
}

export { hhmm };
