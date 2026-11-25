"use client";

import { cn } from "@nexus/ui";

import type { Bag } from "@/lib/backend/client-records";

import type { BagBar } from "./client-v2-model";

const FILL: Record<BagBar["tone"], string> = {
  ok: "bg-series-1",
  warn: "bg-status-warning",
  danger: "bg-status-danger",
};

/**
 * La barra de lo que queda en una bolsa y cuánto dura — spec 072 (2.1–2.3,
 * 2.6). La misma en Clientes y en la ficha. Su nombre accesible es el mismo
 * texto que se ve; el ámbar va en la barra y en su línea, nunca en la fila.
 */
export function BagMeter({
  bag,
  bar,
  label,
  pace,
  size = "sm",
  className,
}: {
  bag: Bag | null;
  bar: BagBar;
  label: string;
  pace: string | null;
  size?: "sm" | "lg";
  className?: string;
}) {
  return (
    <>
      <span
        data-slot="bag-bar"
        data-tone={bar.tone}
        data-state={bag?.state ?? "none"}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(bar.pct)}
        className={cn("block overflow-hidden rounded-full", size === "lg" ? "h-3 w-full" : "h-2", bar.tone === "danger" ? "bg-status-danger-bg" : "bg-muted", className)}
      >
        <span className={cn("block h-full rounded-full", FILL[bar.tone])} style={{ width: `${bar.pct}%` }} />
      </span>
      {pace ? (
        <span data-slot="bag-pace" className={cn(size === "lg" ? "text-ui" : "text-xs", bar.tone === "warn" ? "text-status-warning-text" : "text-muted-foreground")}>
          {pace}
        </span>
      ) : null}
    </>
  );
}
