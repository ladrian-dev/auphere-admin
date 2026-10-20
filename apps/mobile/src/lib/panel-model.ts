/**
 * The Panel's and the Consumo's pure rules, the same as the console's
 * (`apps/console/src/components/home/home-model.ts`), so the phone and the web
 * say the same thing about the same numbers (R4.3).
 */
export type Delta = { kind: "up" | "down" | "same" | "none"; pct: number };

/** Change against the previous period. No previous data: «none», never a fake +100 %. */
export function trendDelta(current: number, previous: number | null): Delta {
  if (previous === null || previous <= 0) return { kind: "none", pct: 0 };
  const pct = Math.round(((current - previous) / previous) * 100);
  if (pct === 0) return { kind: "same", pct: 0 };
  return { kind: pct > 0 ? "up" : "down", pct: Math.abs(pct) };
}

export type CreditRunway = { days: number; monthLeft: number; tone: "positive" | "warning" | "danger" };

/**
 * How many of the days left in the month the balance covers at the 7-day pace.
 * No spend in 7 days, or no balance: no gauge — the card says it in words.
 */
export function creditRunway(available: number | null, daysLeft: number | null, now: Date): CreditRunway | null {
  if (available == null) return null;
  const end = Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1);
  const monthLeft = Math.max(1, Math.ceil((end - now.getTime()) / 86_400_000));
  if (available <= 0 || daysLeft == null) return null;
  const days = Math.min(monthLeft, Math.floor(daysLeft));
  const tone = days >= monthLeft ? "positive" : days < 7 ? "danger" : "warning";
  return { days, monthLeft, tone };
}

/** Shares of a whole, rounded so they add up to exactly 100 (largest remainder). */
export function shares(values: number[]): number[] {
  const total = values.reduce((a, b) => a + b, 0);
  if (total <= 0) return values.map(() => 0);
  const raw = values.map((v) => (v / total) * 100);
  const pcts = raw.map(Math.floor);
  let left = 100 - pcts.reduce((a, b) => a + b, 0);
  const order = raw.map((r, i) => [r - Math.floor(r), i] as const).sort((a, b) => b[0] - a[0]);
  for (const [, i] of order) {
    if (left <= 0) break;
    pcts[i] = (pcts[i] ?? 0) + 1;
    left -= 1;
  }
  return pcts;
}
