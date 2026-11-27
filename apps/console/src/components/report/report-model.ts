import { formatNumber, type BlockChartColumn, type Locale } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import { clientHref } from "@/components/shell/routes-v2";
import type { ClientReport, ReportCause } from "@/lib/backend/client-report";
import { reasonKey } from "@/lib/waiting-reasons";

/**
 * Spec 083 — las cuentas puras del informe de un cliente: hoy y el periodo en la
 * zona del cliente (1.4, 1.7), las fechas que no se pueden pedir (1.5), el enlace
 * que lleva el periodo (1.3), las columnas de la gráfica (2.6) y cómo se escribe
 * cada cifra. Sin React: se prueban solas.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

export type Period = { from: string; to: string };
export type PeriodProblem = "range_reversed" | "range_too_long" | "range_in_future" | "invalid";

/** D13: un trimestre cubre cualquier piloto. La API dice lo mismo. */
export const REPORT_MAX_DAYS = 92;
export const REPORT_DEFAULT_DAYS = 30;
export const REPORT_PRESETS = [7, 30, 90] as const;
export type ReportPreset = (typeof REPORT_PRESETS)[number];

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

function dayMs(iso: string): number | null {
  if (!ISO_DAY.test(iso)) return null;
  const ms = Date.parse(`${iso}T00:00:00Z`);
  // `Date.parse` acepta «2026-02-31» y lo lleva a marzo: se comprueba la vuelta.
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === iso ? ms : null;
}

/** El día de hoy en la zona (`YYYY-MM-DD`); una zona que no existe es UTC, como la API. */
export function todayIn(zone: string, now: Date = new Date()): string {
  const parts = (tz: string) => new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  try {
    return parts(zone);
  } catch {
    return parts("UTC");
  }
}

export function addDays(iso: string, n: number): string {
  const ms = dayMs(iso);
  if (ms === null) return iso;
  return new Date(ms + n * DAY_MS).toISOString().slice(0, 10);
}

/** Los últimos `n` días, hoy incluido. */
export function lastDays(n: number, today: string): Period {
  return { from: addDays(today, -(n - 1)), to: today };
}

/** Sin periodo, los últimos 30 días hasta hoy en la zona del cliente (1.4). */
export function defaultPeriod(zone: string, now: Date = new Date()): Period {
  return lastDays(REPORT_DEFAULT_DAYS, todayIn(zone, now));
}

/** Lo que la API contestaría con 422, dicho antes de pedirlo (1.5). */
export function periodProblem(period: Period, today: string): PeriodProblem | null {
  const from = dayMs(period.from);
  const to = dayMs(period.to);
  const now = dayMs(today);
  if (from === null || to === null || now === null) return "invalid";
  if (to < from) return "range_reversed";
  if ((to - from) / DAY_MS + 1 > REPORT_MAX_DAYS) return "range_too_long";
  if (to > now) return "range_in_future";
  return null;
}

/** El periodo de la dirección (1.3); si falta o no vale, el de por defecto. */
export function readPeriod(raw: { from?: string | string[]; to?: string | string[] }, zone: string, now: Date = new Date()): Period {
  const from = typeof raw.from === "string" ? raw.from : null;
  const to = typeof raw.to === "string" ? raw.to : null;
  if (from && to && periodProblem({ from, to }, todayIn(zone, now)) === null) return { from, to };
  return defaultPeriod(zone, now);
}

/** El atajo que es este periodo (7, 30 o 90 días hasta hoy), o ninguno. */
export function presetOf(period: Period, today: string): ReportPreset | null {
  if (period.to !== today) return null;
  return REPORT_PRESETS.find((n) => lastDays(n, today).from === period.from) ?? null;
}

/** La dirección del informe con su periodo: recargarla o compartirla da el mismo. */
export function reportHref(ref: string, period: Period): string {
  return `${clientHref(ref, "report")}?${new URLSearchParams({ from: period.from, to: period.to }).toString()}`;
}

// ── la gráfica ────────────────────────────────────────────────────────────

const DAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });
const DAY_NUM = new Intl.DateTimeFormat("es-ES", { day: "numeric", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("es-ES", { weekday: "short", timeZone: "UTC" });
const asDate = (iso: string) => new Date(`${iso}T00:00:00Z`);

/**
 * «Conversaciones por día»: resueltas sin persona abajo y con persona encima. Los
 * días ya vienen en la zona del cliente. Hoy se marca solo si el periodo llega a
 * hoy (sin `today` en ninguna, la gráfica daría la última por hoy).
 */
export function reportColumns(t: T, report: Pick<ClientReport["conversations"], "series">, today: string): BlockChartColumn[] {
  const n = report.series.length;
  return report.series.map((d) => {
    const date = asDate(d.day);
    const title = DAY_LONG.format(date);
    const isToday = d.day === today;
    return {
      key: d.day,
      label: isToday ? t("money.chart.today") : n <= 7 ? WEEKDAY.format(date) : DAY_NUM.format(date),
      title: title.charAt(0).toUpperCase() + title.slice(1),
      values: [d.without_person, d.with_person],
      today: isToday,
    };
  });
}

// ── las cifras ────────────────────────────────────────────────────────────

/** «76,2 %», con una cifra decimal como mucho; «—» sin datos. */
export function percentText(t: T, pct: number | null, locale: Locale): string {
  if (pct === null || !Number.isFinite(pct)) return "—";
  return t("report.percent", { n: formatNumber(pct, locale, { maximumFractionDigits: 1 }) });
}

/** ¿Alcanza el objetivo? Sin datos no se juzga. */
export function targetMet(pct: number | null, target: number): boolean | null {
  if (pct === null || !Number.isFinite(pct)) return null;
  return pct >= target;
}

/** «9 s», «1 min 10 s», «2 min». */
export function secondsText(t: T, seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.round(seconds);
  if (total < 60) return t("report.seconds", { n: total });
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s ? t("report.minutesSeconds", { m, s }) : t("report.minutes", { n: m });
}

/**
 * El motivo de una incidencia, en palabras. Las mismas que la Bandeja y
 * Rendimiento (`lib/waiting-reasons.ts`: un flujo por concepto), más el freno de
 * reservas que paró una respuesta y el agente rehízo.
 */
export function causeKey(cause: ReportCause | string): MessageKey {
  if (cause === "booking_brake") return "report.cause.booking_brake";
  return reasonKey(cause) ?? "waiting.reason.other";
}

/** «10 nov 2026»: un día del calendario, sin moverlo de zona. */
export function dayText(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "UTC" }).format(asDate(iso));
}

/** Una hora en la zona del cliente: «26 nov 2026, 11:02». */
export function momentText(iso: string, zone: string, locale: Locale): string {
  const at = new Date(iso);
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: zone }).format(at);
  } catch {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(at);
  }
}
