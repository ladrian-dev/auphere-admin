import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/** «Negocio» mientras llega la ficha (spec 047, T168): la cabecera y las secciones a su tamaño. */
export default async function Loading() {
  const { t } = await getT();
  return (
    <div role="status" aria-label={t("lite.business.loading")} className="grid min-w-0 gap-6">
      <div className="grid gap-2">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-full max-w-lg" />
      </div>
      {[6, 4, 5, 3].map((rows, i) => (
        <div key={i} className="grid min-w-0 gap-3 rounded-md border border-border bg-card p-4 sm:p-6">
          <Skeleton className="h-5 w-40" />
          {Array.from({ length: rows }, (_, r) => (
            <Skeleton key={r} className="h-8 w-full" />
          ))}
        </div>
      ))}
    </div>
  );
}
