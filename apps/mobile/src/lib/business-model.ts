import type { BusinessChange, BusinessSections, Day, Hours, Price, Provenance, Section, Service, Shift } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import type { Locale, MessageKey, T } from "@/i18n/t";

/**
 * Spec 047 (T169; requirements 9, 10, 11, 13, 50.4, 50.5): Negocio on the
 * phone, as plain functions — the week being edited, times, prices, the
 * history and what a refusal means. No rule of the business lives here: the
 * API checks everything again; this only says early what it would say late.
 */
export const DAYS: readonly Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export const MAX_SHIFTS = 6;

export type Week = Record<Day, Shift[]>;

/** The week as the API has it, without `overnight` (the closing time says it). */
export function weekOf(hours: Pick<Hours, "days">): Week {
  const out = {} as Week;
  for (const d of DAYS) out[d] = (hours.days[d] ?? []).map((s) => ({ open: s.open, close: s.close }));
  return out;
}

export function sameWeek(a: Week, b: Week): boolean {
  return DAYS.every((d) => a[d].length === b[d].length && a[d].every((s, i) => s.open === b[d][i]!.open && s.close === b[d][i]!.close));
}

const HHMM = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

/** «24:00» closes at midnight; it is never an opening. */
export function validTime(s: string, closing = false): boolean {
  return HHMM.test(s) || (closing && s === "24:00");
}

/**
 * What a thumb types into what the API reads: «9» → «09:00», «930» →
 * «09:30», «9.30» or «9:3» → «09:30». Anything else is left as typed, and the
 * field says it is wrong.
 */
export function normalizeTime(raw: string): string {
  const s = raw.trim().replace(/h$/i, "").replace(/[.,h]/gi, ":");
  let m = /^(\d{1,2})$/.exec(s);
  if (m) return `${m[1]!.padStart(2, "0")}:00`;
  m = /^(\d{1,2}):(\d{1,2})$/.exec(s);
  if (m) return `${m[1]!.padStart(2, "0")}:${m[2]!.length === 1 ? `${m[2]}0` : m[2]}`;
  m = /^(\d{3,4})$/.exec(s);
  if (m) {
    const digits = m[1]!.padStart(4, "0");
    return `${digits.slice(0, 2)}:${digits.slice(2)}`;
  }
  return raw.trim();
}

const minutes = (s: string) => (s === "24:00" ? 1440 : Number(s.slice(0, 2)) * 60 + Number(s.slice(3)));

export type WeekProblem = { day: Day; code: "invalid_time" | "too_many_shifts" | "overlap"; shift: number | null };

/** The first thing the API would refuse, said before sending (its codes, its words). */
export function checkShifts(day: Day, shifts: Shift[]): WeekProblem | null {
  if (shifts.length > MAX_SHIFTS) return { day, code: "too_many_shifts", shift: null };
  for (let i = 0; i < shifts.length; i++) {
    const s = shifts[i]!;
    if (!validTime(s.open) || !validTime(s.close, true)) return { day, code: "invalid_time", shift: i };
  }
  // Same-day spans in order of opening: one must close before the next opens. A night shift
  // (closing at or before it opens) runs past midnight and is checked by the API against the next day.
  const spans = shifts
    .map((s, i) => ({ i, open: minutes(s.open), close: minutes(s.close) <= minutes(s.open) ? 1440 : minutes(s.close) }))
    .sort((a, b) => a.open - b.open);
  for (let k = 1; k < spans.length; k++) {
    if (spans[k]!.open < spans[k - 1]!.close) return { day, code: "overlap", shift: spans[k]!.i };
  }
  return null;
}

export function checkWeek(week: Week): WeekProblem | null {
  for (const d of DAYS) {
    const p = checkShifts(d, week[d]);
    if (p) return p;
  }
  return null;
}

/** «Por bloques» stays only while Monday to Friday share the same shifts; otherwise day by day, so nothing is lost (10.6). */
export function layoutFor(week: Week, current: Hours["layout"]): "blocks" | "daily" {
  if (current !== "blocks") return "daily";
  const mon = JSON.stringify(week.mon);
  return (["tue", "wed", "thu", "fri"] as const).every((d) => JSON.stringify(week[d]) === mon) ? "blocks" : "daily";
}

/** «09:00–14:00, 17:00–20:00», or «Cerrado». */
export function shiftsText(shifts: readonly Shift[], t: T): string {
  return shifts.length === 0 ? t("business.hours.closed") : shifts.map((s) => `${s.open}–${s.close}`).join(", ");
}

export function dayName(d: Day, t: T): string {
  return t(`business.hours.day.${d}` as MessageKey);
}

// ── fechas ─────────────────────────────────────────────────────────────────

/** A wall date (YYYY-MM-DD) in words: «jueves, 25 de diciembre de 2026». */
export function dateText(d: string, locale: Locale, opts: Intl.DateTimeFormatOptions = { weekday: "long", day: "numeric", month: "long", year: "numeric" }): string {
  return new Date(`${d}T12:00:00Z`).toLocaleDateString(locale, { ...opts, timeZone: "UTC" });
}

/** «25 dic» — or «25 dic 2027» when it is not this year. */
export function shortDate(d: string, locale: Locale, today: string): string {
  const sameYear = d.slice(0, 4) === today.slice(0, 4);
  return dateText(d, locale, sameYear ? { day: "numeric", month: "short" } : { day: "numeric", month: "short", year: "numeric" });
}

export function todayLocal(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

// ── servicios ──────────────────────────────────────────────────────────────

/** The price the API sends (`{kind}` or `{kind: "amount", amount_minor}`), whatever its loose schema says. */
export function priceOf(s: Pick<Service, "price">): Price {
  const p = s.price as { kind?: unknown; amount_minor?: unknown };
  if (p.kind === "amount" && typeof p.amount_minor === "number") return { kind: "amount", amount_minor: p.amount_minor };
  return { kind: p.kind === "free" ? "free" : "none" };
}

/**
 * The Spanish of the country whose currency it is, so a price reads as its
 * customers write it: «$15.000» in Chile, «12,50 €» in Spain. Like Reservas'
 * prices (`features/reservas/format.ts`), which write CLP as «es-CL».
 */
const SPANISH: Record<string, string> = { CLP: "es-CL", EUR: "es-ES", MXN: "es-MX", COP: "es-CO", ARS: "es-AR", PEN: "es-PE", UYU: "es-UY", USD: "es-US" };

/** An amount in minor units, written in the business's currency (CLP has no decimals: `exponent` 0). */
export function moneyText(minor: number, currency: string, exponent: number, locale: Locale): string {
  const value = minor / 10 ** exponent;
  const tag = locale === "es" ? (SPANISH[currency] ?? "es") : "en-US";
  try {
    return new Intl.NumberFormat(tag, { style: "currency", currency, minimumFractionDigits: exponent, maximumFractionDigits: exponent }).format(value);
  } catch {
    return `${value} ${currency}`;
  }
}

export function priceText(price: Price, currency: string, exponent: number, locale: Locale, t: T): string {
  if (price.kind === "amount") return moneyText(price.amount_minor, currency, exponent, locale);
  return price.kind === "free" ? t("business.services.price.free") : t("business.services.price.none");
}

/** What the person types («12,50», «12.5», «15000») into minor units; `null` when it is not an amount. */
export function parseAmount(raw: string, exponent: number): number | null {
  const s = raw.trim().replace(/\s/g, "");
  if (!s) return null;
  // The last «,» or «.» is the decimal mark when it has at most `exponent` digits after it; the rest group thousands.
  const m = /^(\d+(?:[.,]\d{3})*|\d+)(?:[.,](\d+))?$/.exec(s);
  if (!m) return null;
  let whole = m[1]!.replace(/[.,]/g, "");
  let frac = m[2] ?? "";
  if (frac.length > exponent) {
    // «15.000» in a currency without decimals is fifteen thousand.
    if (exponent === 0 && frac.length === 3) {
      whole += frac;
      frac = "";
    } else return null;
  }
  return Number(whole) * 10 ** exponent + Number(frac.padEnd(exponent, "0") || "0");
}

/** The amount as it goes into the field again. */
export function amountField(minor: number, exponent: number, locale: Locale): string {
  const value = minor / 10 ** exponent;
  return exponent === 0 ? String(value) : value.toFixed(exponent).replace(".", locale === "es" ? "," : ".");
}

/** Minutes as typed; `null` for empty, `NaN` for nonsense (the field says it). */
export function parseMinutes(raw: string): number | null {
  const s = raw.trim();
  if (!s) return null;
  return /^\d{1,3}$/.test(s) ? Number(s) : Number.NaN;
}

// ── historial, procedencia y deshacer (13.1, 13.3) ────────────────────────

const SECTIONS: readonly Section[] = ["hours", "special_dates", "services", "locations"];

export function sectionName(section: string, t: T): string {
  return (SECTIONS as readonly string[]).includes(section) ? t(`business.history.section.${section}` as MessageKey) : section;
}

/** The newest change that can still be undone, of one section or of any of the four. */
export function lastUndoable(history: readonly BusinessChange[], section?: Section | Section[]): BusinessChange | null {
  const wanted = section === undefined ? null : Array.isArray(section) ? section : [section];
  return history.find((c) => c.undoable && !c.undone_at && (!wanted || wanted.includes(c.section as Section))) ?? null;
}

/** «Hace 5 min», «hoy a las 10:30», «12 oct»: when, in a few words. */
export function whenText(at: string, now: Date, locale: Locale): string {
  const then = new Date(at);
  const mins = Math.round((now.getTime() - then.getTime()) / 60_000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (mins < 1) return rtf.format(0, "minute");
  if (mins < 60) return rtf.format(-mins, "minute");
  if (mins < 24 * 60) return rtf.format(-Math.round(mins / 60), "hour");
  return then.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

/** «Horario · Marta desde la app · hace 5 minutos». */
export function changeLine(c: BusinessChange, t: T, locale: Locale, now: Date = new Date()): string {
  const section = sectionName(c.section, t);
  const who = c.by?.name ?? t("business.prov.someone");
  const when = whenText(c.at, now, locale);
  const origin = c.origin === "app" ? t("negocio.origin.app") : c.origin === "lite_web" ? t("negocio.origin.lite_web") : null;
  return origin ? t("negocio.change.origin", { section, who, origin, when }) : t("negocio.change", { section, who, when });
}

const READ = new Set(["web", "document", "social", "migrated"]);
const POINTER: Record<Section, string> = { hours: "/hours", special_dates: "/special_dates", services: "/services", locations: "/locations" };

/** Where a datum came from, in the console's words (`provenance-model.ts`): «Editado por Marta desde la app», «Leído de la web · revísalo»… */
export function provenanceText(p: Provenance, t: T): string {
  if (p.source === "person") {
    const name = p.by?.name ?? t("business.prov.someone");
    if (p.origin === "app") return t("business.prov.app", { name });
    if (p.origin === "lite_web") return t("business.prov.lite_web", { name });
    return t("business.prov.person", { name });
  }
  if (READ.has(p.source)) return t(`business.prov.${p.source}${p.review === "pending" ? "" : ".ok"}` as MessageKey);
  if (p.source === "builder" || p.source === "inbox_correction" || p.source === "import") return t(`business.prov.${p.source}` as MessageKey);
  return t("business.prov.someone");
}

/** The provenance that rules a section: the newest of its data (the console's `sectionProvenance`). */
export function sectionProvenance(all: BusinessSections["provenance"], section: Section, item?: string): Provenance | null {
  const prefix = item ? `${POINTER[section]}/${item}` : POINTER[section];
  let best: Provenance | null = null;
  for (const [pointer, p] of Object.entries(all)) {
    if (pointer !== prefix && !pointer.startsWith(`${prefix}/`)) continue;
    if (!best || (p.at ?? "") > (best.at ?? "")) best = p;
  }
  return best;
}

// ── lo que dice la API cuando no ──────────────────────────────────────────

/** `412 revision_conflict`: someone wrote first. The section as it is now, to put in the cache. */
export function conflictOf<S>(e: unknown): { current: S | null } | null {
  if (!(e instanceof ApiError) || e.status !== 412 || e.code !== "revision_conflict") return null;
  return { current: (e.info.current as S | undefined) ?? null };
}

/** A refusal of a write to the business, in the console's words where it has them. */
export function writeErrorText(e: unknown, t: T, section?: Section): string {
  if (!(e instanceof ApiError)) return t("business.section.error.generic");
  if (e.offline) return t("negocio.offline");
  if (e.code === "client_archived") return t("negocio.archived_client");
  if (e.code === "revision_conflict") return t("negocio.conflict");
  const day = typeof e.info.day === "string" && (DAYS as readonly string[]).includes(e.info.day) ? dayName(e.info.day as Day, t) : "";
  switch (e.code) {
    case "invalid_time":
    case "overlap":
    case "overlap_next_day":
    case "too_many_shifts":
      return t(`business.hours.error.${e.code}` as MessageKey, { day });
    case "date_range":
    case "no_shifts":
      return t(`business.special.error.${e.code}` as MessageKey);
    case "duration_required":
    case "duration_invalid":
    case "price_amount_required":
    case "price_invalid":
      return t(`business.services.error.${e.code}` as MessageKey);
    case "name_required":
      return section === "locations" ? t("business.locations.error.name_required") : t("business.services.error.name_required");
    case "phone_invalid":
      return t("business.locations.error.phone_invalid");
    default:
      return t("business.section.error.generic");
  }
}

/** The business sections with one replaced by what the API answered. */
export function withSection<K extends Section>(all: BusinessSections | undefined, section: K, value: BusinessSections[K]): BusinessSections | undefined {
  return all ? { ...all, [section]: value } : all;
}
