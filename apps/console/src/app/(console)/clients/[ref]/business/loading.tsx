import { Skeleton } from "@nexus/ui";

import { BUSINESS_GRID, BUSINESS_INDEX_LIST, BUSINESS_SECTIONS_COLUMN } from "@/components/business/sections/layout";
import { getT } from "@/i18n/server";

/** Las alturas de las primeras tarjetas: Datos básicos (cinco filas), Sedes, Horarios y Servicios. */
const CARDS = ["h-72", "h-36", "h-56", "h-48"] as const;

/**
 * Cargando Negocio (spec 047, T060; T218): la misma rejilla que la página
 * (`layout.ts`), el índice con sus ocho secciones (con Políticas y Preguntas
 * frecuentes, enmienda del 2026-10-29) también en el móvil, donde es una fila,
 * y las primeras tarjetas con su radio y su tamaño, para que nada salte cuando
 * llegan los datos. Se anuncia a los lectores de pantalla.
 */
export default async function BusinessLoading() {
  const { t } = await getT();
  return (
    <div role="status" aria-label={t("business.page.loading")} className={BUSINESS_GRID}>
      <div className="grid min-w-0 gap-3">
        <div className={BUSINESS_INDEX_LIST} data-slot="business-index-skeleton">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-9 w-28 shrink-0 lg:w-full" />
          ))}
        </div>
        <Skeleton className="mx-3 hidden h-8 lg:block" />
      </div>
      <div className={BUSINESS_SECTIONS_COLUMN} data-slot="business-sections-skeleton">
        {CARDS.map((height, i) => (
          <Skeleton key={i} className={`${height} w-full rounded-lg`} />
        ))}
      </div>
    </div>
  );
}
