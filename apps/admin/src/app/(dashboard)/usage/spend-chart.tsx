"use client";

import { StackedBarChart } from "@nexus/ui";

/**
 * Spec 039: each day's sale, split into what the model cost and what Auphere
 * kept — the bar's height is the sale, its top part the profit.
 */
export function SpendChart({
  daily,
}: {
  daily: Array<{ day: string; spend_cents: number; cost_usd: string; profit_usd: string }>;
}) {
  if (daily.length === 0 || daily.every((d) => d.spend_cents === 0 && Number(d.cost_usd) === 0)) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No hubo consumo en este periodo.</p>;
  }
  return (
    <StackedBarChart
      ariaLabel="Coste y ganancia por día"
      data={daily.map((d) => {
        const cost = Math.round(Number(d.cost_usd) * 100);
        return { day: d.day, cost, profit: Math.max(0, d.spend_cents - cost) };
      })}
      xKey="day"
      series={[
        { key: "cost", label: "Coste del modelo" },
        { key: "profit", label: "Ganancia" },
      ]}
      // Short enough for the axis («12,00 $»); the tooltip uses the same.
      formatValue={(n) => `${(n / 100).toLocaleString("es", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`}
      formatX={(x) => new Date(`${x}T00:00:00Z`).toLocaleDateString("es", { day: "numeric", month: "short", timeZone: "UTC" })}
    />
  );
}
