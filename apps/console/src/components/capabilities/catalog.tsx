"use client";

import { Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { CatalogBrowser, EmptyState } from "@nexus/ui";

import { useCatalog, useCatalogLabels } from "@/components/catalog/use-catalog";
import { useT } from "@/i18n/client";
import type { CapabilitiesOut } from "@/lib/backend/capabilities";

import { CapabilityCard } from "./capability-card";

/**
 * Habilidades (spec 017 R5; spec 018 R4): una pantalla donde antes había dos,
 * y desde la spec 018 con **el mismo patrón de navegación** que Conectores y
 * Canales — buscar, activos/todo, filtrar por categoría.
 *
 * Lo que esta pantalla aporta al patrón es lo suyo y nada más: la función de
 * negocio como categoría, la tarjeta con su interruptor y el filtro por
 * sector. El patrón no sabe nada de eso.
 *
 * **Tampoco hay un aviso de conectores que faltan** (owner, 2026-09-28).
 * Lo hubo, encabezando la pantalla: una lista de los conectores sin conectar
 * con lo que desbloquea cada uno. Repetía lo que cada tarjeta ya dice de sí
 * misma —«necesita WooCommerce», con su enlace— y lo repetía arriba del todo,
 * empujando el catálogo entero hacia abajo. Conectores es su pantalla.
 *
 * **No hay encendido en bloque** (owner, 2026-09-28). Lo hubo: dos botones
 * que encendían o apagaban «las visibles». Actuaban sobre un conjunto que
 * dependía del filtro puesto, así que un filtro que no se había mirado
 * volteaba treinta y siete habilidades de una vez, con una llamada por cada
 * una. Encender de una en una es más lento y no se equivoca.
 *
 * El buscador filtra en cliente sobre lo ya cargado: la lista completa son
 * decenas de elementos, no miles, y filtrar en el servidor añadiría una ida
 * y vuelta por cada tecla sin ganar nada.
 */
export function CapabilitiesCatalog({
  refId,
  data,
  canWrite,
  seeAllHref,
  seeOwnHref,
  agentId,
}: {
  refId: string;
  data: CapabilitiesOut;
  canWrite: boolean;
  seeAllHref: string;
  seeOwnHref: string;
  /** Spec 030: one of the client's agents; `undefined` is the principal. */
  agentId?: string;
}) {
  const t = useT();
  const router = useRouter();
  const base = `/clients/${encodeURIComponent(refId)}/capabilities`;
  const catalog = useCatalog(base);
  const labels = useCatalogLabels({
    title: t("cap.title"),
    category: (key) => t(`cap.fn.${key}` as "cap.fn.other"),
  });
  const all = React.useMemo(() => data.groups.flatMap((g) => g.items), [data.groups]);
  // La forma que el patrón entiende. El orden de los grupos lo pone la API,
  // y se conserva porque los elementos llegan en él.
  const items = React.useMemo(
    () =>
      all.map((cap) => ({
        id: `${cap.kind}:${cap.key}`,
        name: cap.business_name,
        search: cap.description,
        category: cap.function,
        active: cap.enabled,
        cap,
      })),
    [all],
  );

  const viewingAll = data.hidden_by_sector === 0 && data.sector !== null;

  return (
    <div className="flex flex-col gap-(--space-section)">
      <CatalogBrowser
        {...catalog}
        items={items}
        labels={labels}
        renderLink={(href, children, props) => (
          <Link href={href} {...props}>
            {children}
          </Link>
        )}
        renderItem={({ id, cap }) => (
          <CapabilityCard key={id} refId={refId} agentId={agentId} cap={cap} canWrite={canWrite} onChanged={() => router.refresh()} />
        )}
        empty={
          // Sin catálogo, las integraciones siguen arriba: hoy el vacío las
          // escondía y no había forma de conectar nada.
          <EmptyState icon={Wrench} title={t("cap.empty.title")} description={t("cap.empty.body")} readonly />
        }
        notice={
          <div className="flex min-w-0 flex-col gap-1">
            {/* El sector es un filtro de esta pantalla, no del patrón: no
                estrecha lo que hay, **ensancha** el catálogo entero. Por eso
                vive aquí y no entre las pastillas. */}
            {data.sector === null ? (
              <p className="text-sm text-muted-foreground">{t("cap.sector.none")}</p>
            ) : viewingAll ? (
              <p className="text-sm text-muted-foreground">
                {t("cap.sector.viewingAll")}{" "}
                <Link href={seeOwnHref} className="underline underline-offset-4">
                  {t("cap.sector.seeOwn")}
                </Link>
              </p>
            ) : data.hidden_by_sector > 0 ? (
              <p className="text-sm text-muted-foreground">
                {data.hidden_by_sector === 1
                  ? t("cap.sector.hiddenOne")
                  : t("cap.sector.hidden", { n: data.hidden_by_sector })}{" "}
                <Link href={seeAllHref} className="underline underline-offset-4">
                  {t("cap.sector.seeAll")}
                </Link>
              </p>
            ) : null}
            {!canWrite ? <p className="text-sm text-muted-foreground">{t("cap.readonly")}</p> : null}
          </div>
        }
      />
    </div>
  );
}
