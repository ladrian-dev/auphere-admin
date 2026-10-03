/**
 * The daily bars (owner's style 3, 2026-10-02): one total per day, today
 * last and marked, and for each day the three series that weighed most —
 * what the hover says. Pure, so the rule is pinned by plain tests. Used for
 * conversations (home) and spend in money (Consumo).
 */
export type DayBar = { day: string; total: number; top: Array<{ label: string; value: number }>; today: boolean };

export type DayBarsInput = {
  days: string[];
  series: number[];
  byClient: Array<{ label: string; series: number[] }>;
};

export function buildDayBars({ days, series, byClient }: DayBarsInput): { bars: DayBar[]; average: number; max: number } {
  const bars = days.map((day, d) => {
    const top = byClient
      .map((c) => ({ label: c.label, value: c.series[d] ?? 0 }))
      .filter((c) => c.value > 0)
      .sort((x, y) => y.value - x.value)
      .slice(0, 3);
    return { day, total: series[d] ?? 0, top, today: d === days.length - 1 };
  });
  const sum = bars.reduce((acc, b) => acc + b.total, 0);
  const average = bars.length ? sum / bars.length : 0;
  const max = Math.max(1, ...bars.map((b) => b.total));
  return { bars, average, max };
}

/** Which day labels to print: all of them up to two weeks, about ten beyond. */
export function showDayLabel(index: number, count: number): boolean {
  if (count <= 14) return true;
  const every = Math.ceil(count / 10);
  return index === count - 1 || (count - 1 - index) % every === 0;
}
