"use client";

import { StackedBarChart } from "@nexus/ui";


/** Spend per day at sale price, every partner together (spec 038). */
export function SpendChart({ daily }: { daily: Array<{ day: string; spend_cents: number }> }) {
  if (daily.length === 0 || daily.every((d) => d.spend_cents === 0)) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Nadie ha gastado saldo en este periodo.</p>;
  }
  return (
    <StackedBarChart
      ariaLabel="Gasto por día"
      data={daily.map((d) => ({ day: d.day, spend: d.spend_cents }))}
      xKey="day"
      series={[{ key: "spend", label: "Gasto" }]}
      // Short enough for the axis («12,00 $»); the tooltip uses the same.
      formatValue={(n) => `${(n / 100).toLocaleString("es", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`}
      formatX={(x) => new Date(`${x}T00:00:00Z`).toLocaleDateString("es", { day: "numeric", month: "short", timeZone: "UTC" })}
    />
  );
}
