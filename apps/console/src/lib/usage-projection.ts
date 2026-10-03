/**
 * Pure helpers of the usage page (CP-22): month projection and chart
 * shaping. No I/O — unit-tested in `__tests__/usage-projection.test.ts`.
 * The backend computes the same linear projection (`services/console_reporting.py`);
 * this mirror exists so the cumulative line can be drawn per day.
 */

export type SeriesPoint = { day: string; by_meter: Record<string, number> };

/** Linear end-of-month projection over the elapsed days (today counts as a day). */
export function projectMonth(units: number, elapsedDays: number, daysInMonth: number): number {
  if (elapsedDays <= 0) return units;
  return Math.round((units / elapsedDays) * daysInMonth * 1000) / 1000;
}

export function percentOf(units: number, cap: number | null): number | null {
  if (cap == null || cap <= 0) return null;
  return Math.round((units / cap) * 10000) / 100;
}

/** Spec 028: the technical detail as a list — one row per meter, grouped,
 *  with its total for the period and its daily series. The model meters
 *  (input, output, cache read, cache write) always have a row: a cache that
 *  reads 0 is a fact worth seeing, not a missing line. */
export type MeterRow = { meter: string; total: number; series: number[] };
export type MeterGroup = { key: "messages" | "model" | "media" | "voice" | "other"; rows: MeterRow[] };

const ALWAYS = ["channel.message", "llm.input_tokens", "llm.output_tokens", "llm.cache_read", "llm.cache_write"];

function groupOf(meter: string): MeterGroup["key"] {
  if (meter === "channel.message") return "messages";
  if (meter.startsWith("llm.")) return "model";
  if (meter.startsWith("media.")) return "media";
  if (meter.startsWith("voice.")) return "voice";
  return "other";
}

export function meterGroups(points: SeriesPoint[], totals: Record<string, number>): MeterGroup[] {
  const meters = new Set<string>([...ALWAYS, ...Object.keys(totals)]);
  for (const p of points) for (const m of Object.keys(p.by_meter)) meters.add(m);
  const order = (m: string) => {
    const i = ALWAYS.indexOf(m);
    return i === -1 ? ALWAYS.length : i;
  };
  const rows = [...meters]
    .sort((a, b) => order(a) - order(b) || a.localeCompare(b))
    .map((meter) => ({ meter, total: totals[meter] ?? points.reduce((sum, p) => sum + (p.by_meter[meter] ?? 0), 0), series: points.map((p) => p.by_meter[meter] ?? 0) }));
  // Messages and media fill one column, the model the other: even heights.
  const keys: MeterGroup["key"][] = ["messages", "media", "voice", "model", "other"];
  return keys.map((key) => ({ key, rows: rows.filter((r) => groupOf(r.meter) === key) })).filter((g) => g.rows.length > 0);
}
