import { Skeleton } from "@nexus/ui";

import { getT } from "@/i18n/server";

/**
 * Cargando «Acceso» (spec 056): las dos tarjetas con su rejilla, su radio y su
 * alto aproximado (el interruptor y los cuatro módulos; el formulario de invitar
 * y tres personas), para que nada salte cuando llegan los datos. Se anuncia a
 * los lectores de pantalla.
 */
export default async function ClientAccessLoading() {
  const { t } = await getT();
  return (
    <div role="status" aria-label={t("clientAccess.loading")} className="grid min-w-0 gap-6 lg:grid-cols-2 lg:items-start">
      <Skeleton className="h-96 w-full rounded-md" data-slot="client-console-skeleton" />
      <Skeleton className="h-80 w-full rounded-md" data-slot="client-people-skeleton" />
    </div>
  );
}
