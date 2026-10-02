import type { AttentionItem, AttentionKind, HomeTrend } from "@/lib/backend/home-usage";

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

/** Tone of a client status badge. */
export function statusTone(status: string): "positive" | "warning" | "danger" | "muted" {
  if (status === "active") return "positive";
  if (status === "provisioning") return "warning";
  if (status === "paused" || status === "suspended") return "danger";
  return "muted";
}

export type ChartData = {
  rows: Array<Record<string, string | number>>;
  series: Array<{ key: string; label: string }>;
};

/** The stacked daily chart: one series per top client, «el resto» last. */
export function chartData(trend: HomeTrend, restLabel: string): ChartData {
  const series = trend.by_client.map((c, i) => ({
    key: `s${i}`,
    label: c.external_client_ref === null ? restLabel : (c.client_name ?? c.external_client_ref),
  }));
  const rows = trend.days.map((day, d) => {
    const row: Record<string, string | number> = { day };
    trend.by_client.forEach((c, i) => {
      row[`s${i}`] = c.series[d] ?? 0;
    });
    return row;
  });
  return { rows, series };
}

/** «Alcanza para unos N días», rounded to what a person would say. */
export function roundDays(days: number): number {
  if (days < 1) return 0;
  if (days < 10) return Math.round(days);
  return Math.round(days / 5) * 5;
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
