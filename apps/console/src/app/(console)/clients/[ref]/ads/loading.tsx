import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/**
 * Cargando «Anuncios» (spec 076): la tarjeta del informe con su título, el
 * selector de periodo y la tabla (cabecera y tres filas), del alto que tendrá,
 * para que nada salte cuando llegan los datos. Se anuncia a los lectores de
 * pantalla.
 */
export default async function ClientAdsLoading() {
  const { t } = await getT();
  return (
    <div role="status" aria-label={t("ads.loading")} className="grid min-w-0 gap-4 rounded-lg border border-border bg-card p-4 sm:px-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-2">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-5 w-80 max-w-full" />
        </div>
        <Skeleton className="h-8 w-48 rounded-full" />
      </div>
      <Skeleton className="h-9 w-full" />
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}
