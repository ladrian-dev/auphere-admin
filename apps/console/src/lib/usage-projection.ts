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

/** Sum of a meter over the whole series. */
export function seriesTotal(points: SeriesPoint[], meter: string): number {
  return points.reduce((acc, p) => acc + (p.by_meter[meter] ?? 0), 0);
}

/** Meters present in the series, biggest first; the rest folded into `other`. */
export function topMeters(points: SeriesPoint[], max = 6): { keys: string[]; hasOther: boolean } {
  const totals = new Map<string, number>();
  for (const p of points) for (const [m, v] of Object.entries(p.by_meter)) totals.set(m, (totals.get(m) ?? 0) + v);
  const sorted = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([m]) => m);
  return { keys: sorted.slice(0, max), hasOther: sorted.length > max };
}

/** Rows for the stacked bars: one per day, series under their meter key (+ `other`). */
export function barsFromSeries(points: SeriesPoint[], keys: string[]): Record<string, string | number>[] {
  const keep = new Set(keys);
  return points.map((p) => {
    const row: Record<string, string | number> = { day: p.day };
    let other = 0;
    for (const [m, v] of Object.entries(p.by_meter)) {
      if (keep.has(m)) row[m] = v;
      else other += v;
    }
    if (other > 0) row.other = other;
    return row;
  });
}

/**
 * Cumulative line of one meter across the natural month + linear projection
 * from today to the last day. `points` may cover more than the month; only
 * days in [monthStart, monthEnd) are used. Returns one point per day of the
 * month: `actual` up to today, `projected` from today (inclusive, so the two
 * lines join) to the end.
 */
export function cumulativeWithProjection(
  points: SeriesPoint[],
  meter: string,
  monthStartIso: string,
  daysInMonth: number,
  todayIso: string,
): { x: string; actual: number | null; projected: number | null }[] {
  const start = new Date(monthStartIso.slice(0, 10) + "T00:00:00Z");
  const byDay = new Map(points.map((p) => [p.day, p.by_meter[meter] ?? 0]));
  const out: { x: string; actual: number | null; projected: number | null }[] = [];
  let acc = 0;
  let todayIndex = -1;
  for (let i = 0; i < daysInMonth; i++) {
    const d = new Date(start.getTime() + i * 86_400_000).toISOString().slice(0, 10);
    if (d <= todayIso) {
      acc += byDay.get(d) ?? 0;
      out.push({ x: d, actual: acc, projected: null });
      if (d === todayIso) todayIndex = i;
    } else {
      out.push({ x: d, actual: null, projected: null });
    }
  }
  if (todayIndex < 0) todayIndex = out.length - 1;
  const elapsed = todayIndex + 1;
  const perDay = elapsed > 0 ? acc / elapsed : 0;
  for (let i = todayIndex; i < out.length; i++) {
    out[i]!.projected = Math.round((acc + perDay * (i - todayIndex)) * 1000) / 1000;
  }
  return out;
}
