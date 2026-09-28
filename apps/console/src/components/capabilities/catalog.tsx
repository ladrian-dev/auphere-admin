"use client";

import { Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, CatalogBrowser, EmptyState } from "@nexus/ui";

import { setCapabilityAction } from "@/app/(console)/clients/[ref]/capabilities/actions";
import { useCatalog, useCatalogLabels } from "@/components/catalog/use-catalog";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { CapabilitiesOut, Capability } from "@/lib/backend/capabilities";

import { BlockingIntegrations } from "./blocking-integrations";
import { CapabilityCard } from "./capability-card";

/**
 * Habilidades (spec 017 R5; spec 018 R4): una pantalla donde antes había dos,
 * y desde la spec 018 con **el mismo patrón de navegación** que Conectores y
 * Canales — buscar, activos/todo, filtrar por categoría.
 *
 * Lo que esta pantalla aporta al patrón es lo suyo y nada más: la función de
 * negocio como categoría, la tarjeta con su interruptor, el filtro por sector
 * y el encendido en bloque. El patrón no sabe nada de eso.
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
}: {
  refId: string;
  data: CapabilitiesOut;
  canWrite: boolean;
  seeAllHref: string;
  seeOwnHref: string;
}) {
  const t = useT();
  const router = useRouter();
  const base = `/clients/${encodeURIComponent(refId)}/capabilities`;
  const catalog = useCatalog(base);
  const labels = useCatalogLabels({
    title: t("cap.title"),
    category: (key) => t(`cap.fn.${key}` as "cap.fn.other"),
  });
  const [bulk, startBulk] = React.useTransition();

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

  /** Encender o apagar todas las visibles: una llamada por capacidad, que es
   *  lo que la API acepta, y solo las que de verdad cambian. */
  function setAllVisible(targets: Capability[], enabled: boolean) {
    const changing = targets.filter((c) => c.enabled !== enabled);
    if (changing.length === 0) return;
    startBulk(async () => {
      let failed = 0;
      for (const cap of changing) {
        const res = await setCapabilityAction({ ref: refId, key: cap.key, kind: cap.kind, enabled });
        if (!res.ok) {
          failed += 1;
          toast.error(actionErrorText(res, t));
          break;
        }
      }
      if (failed === 0) toast.success(t("cap.saved"));
      router.refresh();
    });
  }

  // Lo que el patrón enseñaría ahora mismo: es sobre eso que actúan los dos
  // botones de encendido en bloque, y por eso se calcula aquí y no dentro.
  const visible = React.useMemo(() => {
    const needle = catalog.query.trim().toLowerCase();
    return items
      .filter((i) => {
        if (catalog.tab === "active" && !i.active) return false;
        if (catalog.category !== null && i.category !== catalog.category) return false;
        if (needle && !`${i.name} ${i.search ?? ""}`.toLowerCase().includes(needle)) return false;
        return true;
      })
      .map((i) => i.cap);
  }, [items, catalog.query, catalog.tab, catalog.category]);

  const viewingAll = data.hidden_by_sector === 0 && data.sector !== null;

  return (
    <div className="flex flex-col gap-(--space-section)" aria-busy={bulk}>
      <BlockingIntegrations refId={refId} items={visible} />

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
          <CapabilityCard key={id} refId={refId} cap={cap} canWrite={canWrite} onChanged={() => router.refresh()} />
        )}
        empty={
          // Sin catálogo, las integraciones siguen arriba: hoy el vacío las
          // escondía y no había forma de conectar nada.
          <EmptyState icon={Wrench} title={t("cap.empty.title")} description={t("cap.empty.body")} readonly />
        }
        notice={
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-1">
              {/* El sector es un filtro de esta pantalla, no del patrón: no
                  estrecha lo que hay, **ensancha** el catálogo entero. Por eso
                  vive al lado y no entre las pastillas. */}
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
            {canWrite && visible.length > 0 ? (
              <span className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" disabled={bulk} onClick={() => setAllVisible(visible, true)}>
                  {t("cap.enableVisible")}
                </Button>
                <Button variant="ghost" size="sm" disabled={bulk} onClick={() => setAllVisible(visible, false)}>
                  {t("cap.disableVisible")}
                </Button>
              </span>
            ) : null}
          </div>
        }
      />
    </div>
  );
}
