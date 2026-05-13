/**
 * Block M.5 — reusable list / detail skeletons for Suspense fallbacks.
 *
 * Next.js 15 auto-wraps server components in a Suspense boundary when a
 * sibling ``loading.tsx`` is present. These primitives match the shape of
 * the real layouts so the page doesn't shift on hydrate.
 */

import { Skeleton } from "@/components/ui/skeleton";

export function TableSkeleton({
  rows = 6,
  columns = 4,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <div className="rounded-md border border-border bg-card overflow-hidden">
      <div className="grid grid-cols-[1fr] gap-3 p-4">
        <Skeleton className="h-5 w-1/3" />
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="grid items-center gap-4"
            style={{ gridTemplateColumns: `2fr ${"1fr ".repeat(columns - 1)}` }}
          >
            <div className="flex flex-col gap-1">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
            {Array.from({ length: columns - 1 }).map((_, j) => (
              <Skeleton key={j} className="h-4 w-3/4" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CardSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="rounded-md border border-border bg-card p-6 grid gap-3">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-6 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
      <div className="grid gap-2 pt-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="grid grid-cols-[1fr_2fr] gap-3">
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function HeaderSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-72" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}
