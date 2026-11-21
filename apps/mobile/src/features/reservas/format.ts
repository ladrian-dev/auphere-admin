import type { CalendarState, Pro, Reservation } from "@/api/reservas";
import type { Locale, MessageKey, T } from "@/i18n/t";
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

/**
 * The word over a day in the strips: its short weekday, or «hoy» / «Today» —
 * in the case the locale writes its weekdays in (lower in Spanish, capitalised
 * in English), so «today» never sits small beside «Mon» (review H17).
 */
export function stripWeekday(d: LocalDate, isToday: boolean, t: T, locale: Locale): string {
  const weekday = weekdayShort(d, locale);
  if (!isToday) return weekday;
  const word = t("reservas.today");
  return weekday === weekday.toLocaleLowerCase(locale) ? word.toLocaleLowerCase(locale) : word;
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

/**
 * ISO 4217 minor digits, as the API has them (`services_catalog.exponent`) and
 * the web's `lib/amount.ts` reads them: not Intl's (it says 0 for COP or HUF
 * while the stored minor unit has 2).
 */
const ZERO_DECIMALS = new Set(["BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"]);
const THREE_DECIMALS = new Set(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"]);

export function minorDigits(currency: string): number {
  const code = currency.toUpperCase();
  return ZERO_DECIMALS.has(code) ? 0 : THREE_DECIMALS.has(code) ? 3 : 2;
}

/**
 * A price of the business (spec 069, R14.4, R21.1): the API sends it in the
 * currency's minor unit (`amount_minor`), so 18000 CLP is $18.000 and 1850
 * EUR is 18,50 €. Spanish is Chile's for its own peso (the pilot), and plain
 * Spanish for the rest («18,50 €», not «EUR 18,50»).
 */
export function price(amountMinor: number, currency: string, locale: Locale): string {
  const digits = minorDigits(currency);
  const value = amountMinor / 10 ** digits;
  const tag = locale === "es" ? (currency.toUpperCase() === "CLP" ? "es-CL" : "es") : "en-US";
  try {
    return new Intl.NumberFormat(tag, { style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  } catch {
    // A code Intl refuses: the number in the language and its code, never ×100.
    return `${new Intl.NumberFormat(tag, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)} ${currency}`;
  }
}

/**
 * A professional's Google calendar, in words (spec 069, R13.7): every state
 * the API keeps — connected, waiting for them to authorize, a calendar still
 * to choose, to connect again, or failing — and, beside it, when the
 * business's own Google still blocks their hours. A team read without the
 * state (an older answer) says what `calendar` says.
 */
export function calendarText(p: Pro, t: T): string {
  const state: CalendarState = p.calendarState ?? (p.calendar === "google" ? "connected" : "none");
  const text = t(CALENDAR_KEY[state]);
  return p.calendarBusy ? t("reservas.calendar.withBusy", { state: text }) : text;
}

const CALENDAR_KEY: Record<CalendarState, MessageKey> = {
  connected: "reservas.settings.team.google",
  none: "reservas.settings.team.none",
  pending: "reservas.calendar.pending",
  needs_calendar: "reservas.calendar.needs_calendar",
  needs_reauth: "reservas.calendar.needs_reauth",
  error: "reservas.calendar.error",
};

/** The states that need someone to act: said on the day too, not only in Ajustes. */
export function calendarNeedsAttention(p: Pick<Pro, "calendarState">): boolean {
  return p.calendarState === "needs_calendar" || p.calendarState === "needs_reauth" || p.calendarState === "error";
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
