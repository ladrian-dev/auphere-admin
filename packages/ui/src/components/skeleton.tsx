import type { ComponentProps } from "react";

import { cn } from "../lib/utils";

/** Loading placeholder. Always sized to the final dimensions of what it stands for. */
function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

/** Table-shaped skeleton: header + ``rows`` rows with ``columns`` cells. */
function TableSkeleton({ rows = 6, columns = 4, className }: { rows?: number; columns?: number; className?: string }) {
  const template = `2fr ${"1fr ".repeat(Math.max(columns - 1, 0))}`.trim();
  return (
    <div data-slot="table-skeleton" role="status" aria-label="Loading" className={cn("w-full min-w-0 space-y-2", className)}>
      <div className="grid gap-4 border-b border-border pb-2" style={{ gridTemplateColumns: template }}>
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={i} className="h-4 w-20" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="grid gap-4 py-2" style={{ gridTemplateColumns: template }}>
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton key={c} className={cn("h-4", c === 0 ? "w-3/4" : "w-1/2")} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Eyebrow + title + description, mirroring PageHeader. */
function HeaderSkeleton({ className }: { className?: string }) {
  return (
    <div data-slot="header-skeleton" role="status" aria-label="Loading" className={cn("space-y-3 border-b border-border pb-6", className)}>
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-72 max-w-full" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}

/** Card-shaped skeleton with ``lines`` text lines. */
function CardSkeleton({ lines = 4, className }: { lines?: number; className?: string }) {
  return (
    <div data-slot="card-skeleton" role="status" aria-label="Loading" className={cn("space-y-3 rounded-md bg-card p-4 ring-1 ring-foreground/10", className)}>
      <Skeleton className="h-4 w-1/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3", i % 3 === 2 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export { CardSkeleton, HeaderSkeleton, Skeleton, TableSkeleton };
