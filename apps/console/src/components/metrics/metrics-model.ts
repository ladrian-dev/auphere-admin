import { formatNumber, type BlockChartColumn, type Locale } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";
import type { ClientReport, ReportCause } from "@/lib/backend/client-report";
import { can, type Role } from "@/lib/permissions";
import { reasonKey } from "@/lib/waiting-reasons";

/**
 * Spec 083, enmienda del 2026-11-27 — el modelo de la sección «Conversaciones» de
 * Métricas: el periodo y el anterior (D19), las diferencias (requisito 12), las
 * columnas de las tres gráficas (2.6 y 13.2) y quién ve la sección (D17 y D18).
 * Puro: lo prueban `__tests__/metrics-model.test.ts` y la sección.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

export type Period = { from: string; to: string };

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

function dayMs(iso: string): number | null {
  if (!ISO_DAY.test(iso)) return null;
  const ms = Date.parse(`${iso}T00:00:00Z`);
  // `Date.parse` acepta «2026-02-31» y lo lleva a marzo: se comprueba la vuelta.
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === iso ? ms : null;
}

/** Hoy en el calendario del cliente (`YYYY-MM-DD`). Una zona que no existe es UTC, como en la API. */
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

/**
 * Los últimos `days` días hasta hoy en la zona del cliente y los `days` días justo
 * antes (D19). Con 90 días, el anterior empieza 179 días atrás: los dos caben en
 * los 92 que acepta la API.
 */
export function metricsPeriods(days: number, today: string): { current: Period; previous: Period } {
  const current = { from: addDays(today, -(days - 1)), to: today };
  return { current, previous: { from: addDays(current.from, -days), to: addDays(current.from, -1) } };
}

// ── quién ve la sección ──────────────────────────────────────────────────────

/**
 * D17 y D18: la sección solo existe con `conversations:read` (la pantalla ya pide
 * `usage:read`), y sus cifras son de un cliente. Sin cliente elegido, pide uno.
 */
export function conversationsAccess(role: Role, client: string): "hidden" | "choose" | "show" {
  if (!can(role, "conversations:read") || !can(role, "usage:read")) return "hidden";
  return client ? "show" : "choose";
}

// ── las diferencias (requisito 12) ──────────────────────────────────────────

export type Delta = { kind: "pct" | "points" | "seconds" | "money"; value: number };

/** Recuentos: la variación en porcentaje. Sin nada antes, no hay con qué comparar (12.2). */
export function countDelta(current: number, previous: number | null | undefined): Delta | null {
  if (previous === null || previous === undefined || previous <= 0) return null;
  return { kind: "pct", value: ((current - previous) / previous) * 100 };
}

/** Porcentajes: la diferencia en puntos. Si falta uno de los dos, ninguna (12.2). */
export function pointsDelta(current: number | null, previous: number | null | undefined): Delta | null {
  if (current === null || previous === null || previous === undefined) return null;
  return { kind: "points", value: current - previous };
}

/** Tiempos: la diferencia en segundos. */
export function secondsDelta(current: number | null, previous: number | null | undefined): Delta | null {
  if (current === null || previous === null || previous === undefined) return null;
  return { kind: "seconds", value: current - previous };
}

/** Una diferencia que, redondeada como se enseña, es cero: «igual». */
export function deltaIsZero(delta: Delta): boolean {
  return Number(delta.value.toFixed(delta.kind === "points" ? 1 : 0)) === 0;
}

/**
 * La diferencia como se dice: el signo y el número, sin juicio (12.4). «+7 %»,
 * «−1,2 puntos», «+2 s». Lo que redondea a cero, «igual».
 */
export function deltaText(t: T, delta: Delta, locale: Locale): string {
  const digits = delta.kind === "points" ? 1 : 0;
  const rounded = Number(delta.value.toFixed(digits));
  if (rounded === 0) return t("metrics.delta.same");
  const sign = rounded > 0 ? "+" : "−";
  const n = formatNumber(Math.abs(rounded), locale, { maximumFractionDigits: digits });
  if (delta.kind === "points") return `${sign}${t(Math.abs(rounded) === 1 ? "metrics.unit.point" : "metrics.unit.points", { n })}`;
  if (delta.kind === "seconds") return `${sign}${t("metrics.unit.seconds", { n })}`;
  return `${sign}${t("metrics.unit.pct", { n })}`;
}

// ── las gráficas ────────────────────────────────────────────────────────────

const DAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });
const DAY_NUM = new Intl.DateTimeFormat("es-ES", { day: "numeric", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("es-ES", { weekday: "short", timeZone: "UTC" });
const WEEKDAY_LONG = new Intl.DateTimeFormat("es-ES", { weekday: "long", timeZone: "UTC" });
const asDate = (iso: string) => new Date(`${iso}T00:00:00Z`);
const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Por día (2.6): una columna por fecha, sin persona abajo y con persona encima. */
export function dayColumns(t: T, report: Pick<ClientReport["conversations"], "series">, today: string): BlockChartColumn[] {
  const n = report.series.length;
  return report.series.map((d) => {
    const date = asDate(d.day);
    const isToday = d.day === today;
    return {
      key: d.day,
      label: isToday ? t("money.chart.today") : n <= 7 ? WEEKDAY.format(date) : DAY_NUM.format(date),
      title: capital(DAY_LONG.format(date)),
      values: [d.without_person, d.with_person],
      today: isToday,
    };
  });
}

/** Por hora del día (13.2): 24 columnas; se rotula una de cada tres para que quepa a 360 px. */
export function hourColumns(report: Pick<ClientReport["conversations"], "by_hour">): BlockChartColumn[] {
  return report.by_hour.map((h) => ({
    key: String(h.hour),
    label: h.hour % 3 === 0 ? String(h.hour) : "",
    title: `${String(h.hour).padStart(2, "0")}:00–${String(h.hour).padStart(2, "0")}:59`,
    values: [h.without_person, h.with_person],
    // Sin `today: false`, la gráfica marca la última columna como hoy.
    today: false,
  }));
}

/** Por día de la semana (13.2): del lunes al domingo, como da la API (ISO). */
export function weekdayColumns(report: Pick<ClientReport["conversations"], "by_weekday">): BlockChartColumn[] {
  // El 5 de enero de 2026 fue lunes: ISO 1 → 5 de enero, 7 → 11 de enero.
  return report.by_weekday.map((w) => {
    const date = asDate(`2026-01-${String(4 + w.weekday).padStart(2, "0")}`);
    return { key: String(w.weekday), label: WEEKDAY.format(date), title: capital(WEEKDAY_LONG.format(date)), values: [w.without_person, w.with_person], today: false };
  });
}

// ── las cifras ──────────────────────────────────────────────────────────────

export function percentText(t: T, pct: number | null, locale: Locale): string {
  if (pct === null || !Number.isFinite(pct)) return "—";
  return t("metrics.percent", { n: formatNumber(pct, locale, { maximumFractionDigits: 1 }) });
}

/** El objetivo se alcanza con el mismo número. Sin datos no se juzga. */
export function targetMet(pct: number | null, target: number): boolean | null {
  if (pct === null || !Number.isFinite(pct)) return null;
  return pct >= target;
}

export function secondsText(t: T, seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const total = Math.round(seconds);
  if (total < 60) return t("metrics.seconds", { n: total });
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s ? t("metrics.minutesSeconds", { m, s }) : t("metrics.minutes", { n: m });
}

/** Cada motivo con sus palabras: los de la Bandeja y el freno (D7). */
export function causeKey(cause: ReportCause | string): MessageKey {
  if (cause === "booking_brake") return "metrics.cause.booking_brake";
  return reasonKey(cause) ?? "waiting.reason.other";
}

export function dayText(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "UTC" }).format(asDate(iso));
}

export function momentText(iso: string, zone: string, locale: Locale): string {
  const at = new Date(iso);
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: zone }).format(at);
  } catch {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(at);
  }
}
