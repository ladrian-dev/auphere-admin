import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/**
 * Reservas while its first read is on the way (spec 043, T022): the real
 * frame at the real sizes — the header with its buttons, the three tabs, the
 * toolbar, and a grid of 30-min rows (28 px) under four columns.
 */
export default async function Loading() {
  const { t } = await getT();
  return (
    <div role="status" aria-label={t("reservas.loading")} className="flex min-w-0 flex-col gap-6">
      <div className="flex min-w-0 flex-col gap-3 border-b border-border pb-3 md:flex-row md:items-end md:justify-between">
        <Skeleton className="h-7 w-40" />
        <div className="flex flex-wrap gap-2">
          <Skeleton className="h-8 w-48 rounded-full" />
          <Skeleton className="h-8 w-36" />
        </div>
      </div>
      <div className="flex gap-4 border-b border-border pb-2">
        <Skeleton className="h-6 w-20" />
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-6 w-16" />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Skeleton className="h-7 w-16" />
        <Skeleton className="size-7" />
        <Skeleton className="size-7" />
        <Skeleton className="h-5 w-48" />
        <div className="flex gap-2 md:ml-auto">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="h-9 w-40" />
        </div>
      </div>
      <div className="min-w-0 overflow-hidden rounded-md border border-border bg-card">
        <div className="grid grid-cols-[3.5rem_repeat(4,minmax(10rem,1fr))]">
          <div className="border-b border-border" />
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex items-center gap-2 border-b border-l border-border px-3 py-2">
              <Skeleton className="size-8 rounded-full" />
              <div className="flex flex-col gap-1">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          ))}
          {Array.from({ length: 12 }, (_, r) => (
            <div key={r} className="contents">
              <div className="h-7" />
              {Array.from({ length: 4 }, (_, c) => (
                <div key={c} className="h-7 border-l border-t border-border-soft" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
