import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Skeleton } from "./skeleton";
import { Sparkline } from "./sparkline";

type MetricDelta = {
  /** Already formatted: «+18 %», «−4 pts». */
  label: ReactNode;
  /** Whether the change is good news, bad news or neither. */
  tone: "positive" | "negative" | "neutral";
  /** Screen-reader text, e.g. «18 % más que los 7 días anteriores». */
  srLabel?: string;
};

type MetricProps = {
  label: ReactNode;
  /** Already formatted (Intl). Numbers are never formatted inside. */
  value: ReactNode;
  /** Secondary line: "of 40", "+12 % vs last month", a link. */
  hint?: ReactNode;
  /** Renders the loading state at the final dimensions. */
  loading?: boolean;
  /** Renders as a link/button target: the whole tile is clickable. */
  href?: string;
  /** Spec 026: change against the previous period, shown next to the value. */
  delta?: MetricDelta;
  /** Spec 026: a small trend under the value (oldest first). */
  trend?: { values: number[]; ariaLabel: string };
  className?: string;
};

const DELTA_TONE = {
  positive: "bg-status-positive/15 text-foreground",
  negative: "bg-status-danger/15 text-foreground",
  neutral: "bg-muted text-muted-foreground",
} as const;

/**
 * A single figure with a label. Tabular numerals, no decoration; the tile
 * is a link when ``href`` is given (every figure on the home page must be
 * actionable or absent — PLAN-CONSOLE-V1 CP-08).
 */
function Metric({ label, value, hint, loading, href, delta, trend, className }: MetricProps) {
  const body = (
    <>
      {/* El nombre de una métrica es texto de interfaz: Helvena, no mono. */}
      <p className="text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{label}</p>
      {loading ? (
        <Skeleton className="h-8 w-24" />
      ) : (
        <div className="flex min-w-0 items-baseline gap-2">
          <p className="min-w-0 truncate text-2xl font-semibold tabular-nums" title={typeof value === "string" ? value : undefined}>
            {value}
          </p>
          {delta ? (
            <span className={cn("shrink-0 rounded-full px-2 text-xs font-medium tabular-nums", DELTA_TONE[delta.tone])} data-slot="metric-delta">
              <span aria-hidden={delta.srLabel ? true : undefined}>{delta.label}</span>
              {delta.srLabel ? <span className="sr-only">{delta.srLabel}</span> : null}
            </span>
          ) : null}
        </div>
      )}
      {trend && !loading ? <Sparkline values={trend.values} ariaLabel={trend.ariaLabel} /> : null}
      {hint ? (
        loading ? <Skeleton className="h-4 w-32" /> : <p className="min-w-0 truncate text-sm text-muted-foreground">{hint}</p>
      ) : null}
    </>
  );
  const classes = cn(
    "flex min-w-0 flex-col gap-1 rounded-md bg-card p-4 ring-1 ring-foreground/10",
    href && "transition-colors hover:ring-primary/60 focus-visible:ring-primary",
    className,
  );
  if (href) {
    return (
      <a data-slot="metric" href={href} className={classes} aria-busy={loading || undefined}>
        {body}
      </a>
    );
  }
  return (
    <div data-slot="metric" className={classes} aria-busy={loading || undefined}>
      {body}
    </div>
  );
}

export { Metric, type MetricDelta, type MetricProps };
