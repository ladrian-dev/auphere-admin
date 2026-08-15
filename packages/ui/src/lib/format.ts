/**
 * Formatting helpers — every number, date and unit the console shows goes
 * through ``Intl`` with the ACTIVE locale (PLAN-CONSOLE-V1 §5). Nothing
 * hand-rolls a thousands separator or a currency symbol.
 *
 * ``locale`` defaults to ``es``; the app passes the user's locale.
 */

export type Locale = "es" | "en";

const EM_DASH = "—";

function toDate(input: string | Date | null | undefined): Date | null {
  if (input == null) return null;
  const d = typeof input === "string" ? new Date(input) : input;
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatNumber(value: number | null | undefined, locale: Locale = "es", options?: Intl.NumberFormatOptions): string {
  if (value == null || Number.isNaN(value)) return EM_DASH;
  return new Intl.NumberFormat(locale, options).format(value);
}

export function formatCompact(value: number | null | undefined, locale: Locale = "es"): string {
  return formatNumber(value, locale, { notation: "compact", maximumFractionDigits: 1 });
}

export function formatPercent(ratio: number | null | undefined, locale: Locale = "es"): string {
  if (ratio == null || Number.isNaN(ratio)) return EM_DASH;
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 }).format(ratio);
}

export function formatCurrency(amount: number | null | undefined, currency = "USD", locale: Locale = "es"): string {
  if (amount == null || Number.isNaN(amount)) return EM_DASH;
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
}

export function formatDateTime(input: string | Date | null | undefined, locale: Locale = "es"): string {
  const d = toDate(input);
  if (!d) return EM_DASH;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export function formatDate(input: string | Date | null | undefined, locale: Locale = "es"): string {
  const d = toDate(input);
  if (!d) return EM_DASH;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(d);
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 30],
  ["month", 12],
  ["year", Infinity],
];

export function formatRelative(input: string | Date | null | undefined, locale: Locale = "es", now: Date = new Date()): string {
  const d = toDate(input);
  if (!d) return EM_DASH;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  let diff = (d.getTime() - now.getTime()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(diff) < size) return rtf.format(Math.round(diff), unit);
    diff /= size;
  }
  return rtf.format(Math.round(diff), "year");
}

export function formatDuration(seconds: number | null | undefined, locale: Locale = "es"): string {
  if (seconds == null || Number.isNaN(seconds)) return EM_DASH;
  const nf = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  if (seconds < 60) return `${nf.format(seconds)} s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${nf.format(minutes)} min`;
  const hours = minutes / 60;
  if (hours < 24) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(hours)} h`;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(hours / 24)} d`;
}

export function formatLatency(ms: number | null | undefined, locale: Locale = "es"): string {
  if (ms == null || Number.isNaN(ms)) return EM_DASH;
  if (ms < 1000) return `${formatNumber(Math.round(ms), locale)} ms`;
  return `${formatNumber(ms / 1000, locale, { maximumFractionDigits: 1 })} s`;
}

export function formatBytes(bytes: number | null | undefined, locale: Locale = "es"): string {
  if (bytes == null || Number.isNaN(bytes)) return EM_DASH;
  if (bytes < 1024) return `${formatNumber(bytes, locale)} B`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, locale, { maximumFractionDigits: 0 })} kB`;
  if (bytes < 1024 ** 3) return `${formatNumber(bytes / 1024 ** 2, locale, { maximumFractionDigits: 1 })} MB`;
  return `${formatNumber(bytes / 1024 ** 3, locale, { maximumFractionDigits: 2 })} GB`;
}

export { EM_DASH };
