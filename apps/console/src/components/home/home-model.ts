import type { AttentionItem, AttentionKind, HomeTrend, SpendShare } from "@/lib/backend/home-usage";

/**
 * Pure presentation rules of the home page (spec 026). No React here, so
 * every rule the screen depends on is pinned by a plain test.
 */

export type Delta = { kind: "up" | "down" | "same" | "none"; pct: number };

/** Change against the previous period. No previous data: «none», never a fake +100 %. */
export function trendDelta(current: number, previous: number | null): Delta {
  if (previous === null || previous <= 0) return { kind: "none", pct: 0 };
  const pct = Math.round(((current - previous) / previous) * 100);
  if (pct === 0) return { kind: "same", pct: 0 };
  return { kind: pct > 0 ? "up" : "down", pct: Math.abs(pct) };
}

export type DayBar = { day: string; total: number; top: Array<{ label: string; value: number }>; today: boolean };

/**
 * The daily bars (style 3, chosen by the owner): one total per day, today
 * last and marked, and for each day the three clients that talked most —
 * what the hover says, instead of a stack of colours nobody can read.
 */
export function dayBars(trend: HomeTrend, restLabel: string): { bars: DayBar[]; average: number; max: number } {
  const bars = trend.days.map((day, d) => {
    const top = trend.by_client
      .map((c) => ({ label: c.external_client_ref === null ? restLabel : (c.client_name ?? c.external_client_ref), value: c.series[d] ?? 0 }))
      .filter((c) => c.value > 0)
      .sort((x, y) => y.value - x.value)
      .slice(0, 3);
    return { day, total: trend.series[d] ?? 0, top, today: d === trend.days.length - 1 };
  });
  const average = bars.length ? trend.current / bars.length : 0;
  const max = Math.max(1, ...bars.map((b) => b.total));
  return { bars, average, max };
}

export type AttentionRow =
  | { type: "one"; item: AttentionItem }
  | { type: "many"; kind: AttentionKind; severity: number; names: string[]; count: number; href: string }
  | { type: "wallet"; names: string[]; href: string };

/** Clients from which the same problem is said once, not once per client. */
export const GROUP_FROM = 3;

/** Where a problem shared by many clients is fixed for all of them. */
function groupHref(kind: AttentionKind): string {
  return kind === "out_of_quota" ? "/usage" : "/clients";
}

/**
 * The «Necesita tu atención» rows: one per client and problem, except when
 * several clients share a problem — then one row names them all, so thirteen
 * clients out of credit read as one thing to do, not thirteen. With the
 * partner's own credit at zero no client can answer and no allocation can
 * fix it: that is one partner-level row, first.
 */
export function attentionRows(items: AttentionItem[], walletEmpty = false): AttentionRow[] {
  const rows: AttentionRow[] = [];
  if (walletEmpty) {
    const blocked = items.filter((i) => i.kind === "out_of_quota");
    if (blocked.length > 0) rows.push({ type: "wallet", names: blocked.map((i) => i.client_name ?? i.external_client_ref), href: "/usage" });
    items = items.filter((i) => i.kind !== "out_of_quota");
  }
  const byKind = new Map<AttentionKind, AttentionItem[]>();
  for (const item of items) byKind.set(item.kind, [...(byKind.get(item.kind) ?? []), item]);
  const done = new Set<AttentionKind>();
  for (const item of items) {
    const same = byKind.get(item.kind) ?? [];
    if (same.length < GROUP_FROM) {
      rows.push({ type: "one", item });
      continue;
    }
    if (done.has(item.kind)) continue;
    done.add(item.kind);
    rows.push({
      type: "many",
      kind: item.kind,
      severity: item.severity,
      names: same.map((i) => i.client_name ?? i.external_client_ref),
      count: same.reduce((sum, i) => sum + (i.count ?? 0), 0),
      href: groupHref(item.kind),
    });
  }
  return rows;
}

/** Spend slices with their share of the month, rounded so they add up to 100. */
export function spendShares(shares: SpendShare[]): Array<SpendShare & { pct: number }> {
  const total = shares.reduce((sum, s) => sum + s.cents, 0);
  if (total <= 0) return [];
  const raw = shares.map((s) => (s.cents / total) * 100);
  const pcts = raw.map(Math.floor);
  let left = 100 - pcts.reduce((a, b) => a + b, 0);
  const order = raw.map((r, i) => [r - Math.floor(r), i] as const).sort((a, b) => b[0] - a[0]);
  for (const [, i] of order) {
    if (left <= 0) break;
    pcts[i]! += 1;
    left -= 1;
  }
  return shares.map((s, i) => ({ ...s, pct: pcts[i]! }));
}

export type CreditRunway = { days: number; monthLeft: number; tone: "positive" | "warning" | "danger" };

/**
 * The credit gauge (style E): how many of the days left in the month the
 * credit covers at the 7-day pace. Full bar = it lasts the month. No spend
 * in 7 days: no gauge, there is no pace to measure against. Empty credit:
 * no gauge either, the card says it in words.
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
