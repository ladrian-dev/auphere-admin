/**
 * Date / number / status formatters used across the panel.
 *
 * Rule: every relative time MUST go through ``relativeTime`` so the
 * panel's tone stays consistent ("hace 2 min" vs "2 minutes ago" vs
 * raw ISO strings would be unsightly mixed).
 */

const ES_RTF = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
const ES_DTF = new Intl.DateTimeFormat("es", {
  dateStyle: "medium",
  timeStyle: "short",
});

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 30],
  ["month", 12],
  ["year", Infinity],
];

export function relativeTime(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const date = typeof input === "string" ? new Date(input) : input;
  let delta = (date.getTime() - Date.now()) / 1000;
  let unit: Intl.RelativeTimeFormatUnit = "second";
  for (const [u, divisor] of UNITS) {
    if (Math.abs(delta) < divisor) {
      unit = u;
      break;
    }
    delta /= divisor;
    unit = u;
  }
  return ES_RTF.format(Math.round(delta), unit);
}

export function fullDateTime(input: string | Date | null | undefined): string {
  if (!input) return "—";
  const date = typeof input === "string" ? new Date(input) : input;
  return ES_DTF.format(date);
}

export function planLabel(plan: string): string {
  switch (plan) {
    case "essential":
      return "Esencial";
    case "pro":
      return "Pro";
    case "business":
      return "Business";
    case "internal":
      return "Interno";
    default:
      return plan;
  }
}

/** Latency in ms → "423 ms" / "1.2 s" — small enough to live in the
 *  message bubble footer next to cost. */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Cost in USD → "$0.0042" with up to 4 decimal places for small
 *  numbers, 2 for ≥$1 so totals read naturally. */
export function formatCostUsd(usd: number | null | undefined): string {
  if (usd === null || usd === undefined) return "—";
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  if (usd === 0) return "$0";
  return `$${usd.toFixed(4)}`;
}

/** Byte count → "12 kB" / "3.4 MB". WhatsApp media is rarely >50 MB so
 *  GB is intentionally absent. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function statusLabel(status: string): string {
  switch (status) {
    case "active":
      return "Activo";
    case "paused":
      return "Pausado";
    case "archived":
      return "Archivado";
    case "suspended":
      return "Suspendido";
    case "escalated":
      return "Escalado";
    case "open":
      return "Abierto";
    case "closed":
      return "Cerrado";
    default:
      return status;
  }
}
