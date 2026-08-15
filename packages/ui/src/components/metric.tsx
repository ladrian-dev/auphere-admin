import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { Skeleton } from "./skeleton";

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
  className?: string;
};

/**
 * A single figure with a label. Tabular numerals, no decoration; the tile
 * is a link when ``href`` is given (every figure on the home page must be
 * actionable or absent — PLAN-CONSOLE-V1 CP-08).
 */
function Metric({ label, value, hint, loading, href, className }: MetricProps) {
  const body = (
    <>
      <p className="font-mono text-xs tracking-eyebrow text-muted-foreground uppercase">{label}</p>
      {loading ? (
        <Skeleton className="h-8 w-24" />
      ) : (
        <p className="min-w-0 truncate text-2xl font-semibold tabular-nums" title={typeof value === "string" ? value : undefined}>
          {value}
        </p>
      )}
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

export { Metric, type MetricProps };
