import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/** «Agentes» mientras llega la lista (spec 047, T168): la cabecera y dos tarjetas de su tamaño. */
export default async function Loading() {
  const { t } = await getT();
  return (
    <div role="status" aria-label={t("lite.agents.loading")} className="grid min-w-0 gap-6">
      <div className="grid gap-2">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-full max-w-md" />
      </div>
      {Array.from({ length: 2 }, (_, i) => (
        <div key={i} className="grid min-w-0 gap-4 rounded-md border border-border bg-card p-4 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-36" />
              <Skeleton className="h-5 w-24 rounded-full" />
            </div>
            <Skeleton className="h-8 w-24" />
          </div>
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-9 w-full" />
        </div>
      ))}
    </div>
  );
}
