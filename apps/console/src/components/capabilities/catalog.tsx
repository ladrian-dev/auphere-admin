"use client";

import { Search, Wrench } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, EmptyState, Input, Section } from "@nexus/ui";

import { setCapabilityAction } from "@/app/(console)/clients/[ref]/capabilities/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { CapabilitiesOut, CapabilityFunction } from "@/lib/backend/capabilities";

import { BlockingIntegrations } from "./blocking-integrations";
import { CapabilityCard } from "./capability-card";

/**
 * Capacidades (spec 017, R5): una pantalla donde antes había dos.
 *
 * Agrupa por lo que el negocio quiere conseguir, no por si por dentro es
 * herramienta o habilidad. El sector del cliente decide qué se ve por
 * defecto, y la pantalla dice cuántas esconde para que «Ver todas» sea una
 * elección informada.
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
  const [q, setQ] = React.useState("");
  const [bulk, startBulk] = React.useTransition();

  const all = React.useMemo(() => data.groups.flatMap((g) => g.items), [data.groups]);
  const needle = q.trim().toLowerCase();
  const visible = React.useMemo(
    () =>
      needle
        ? all.filter((c) => `${c.business_name} ${c.description}`.toLowerCase().includes(needle))
        : all,
    [all, needle],
  );
  const on = visible.filter((c) => c.enabled).length;
  const viewingAll = data.hidden_by_sector === 0 && data.sector !== null;

  /** Encender o apagar todas las visibles: una llamada por capacidad, que es
   *  lo que la API acepta, y solo las que de verdad cambian. */
  function setAllVisible(enabled: boolean) {
    const targets = visible.filter((c) => c.enabled !== enabled);
    if (targets.length === 0) return;
    startBulk(async () => {
      let failed = 0;
      for (const cap of targets) {
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

  const groups = React.useMemo(() => {
    const byFn = new Map<CapabilityFunction, typeof visible>();
    for (const c of visible) byFn.set(c.function, [...(byFn.get(c.function) ?? []), c]);
    return data.groups.filter((g) => byFn.has(g.function)).map((g) => ({ fn: g.function, items: byFn.get(g.function)! }));
  }, [data.groups, visible]);

  return (
    <div className="flex flex-col gap-(--space-section)" aria-busy={bulk}>
      <BlockingIntegrations refId={refId} items={visible} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <label htmlFor="cap-q" className="sr-only">
            {t("cap.search.label")}
          </label>
          <span className="relative inline-flex items-center">
            <Search aria-hidden="true" className="absolute left-3 size-4 text-muted-foreground" />
            <Input
              id="cap-q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("cap.search")}
              className="w-72 pl-9"
            />
          </span>
          <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
            {t("cap.count", { on, total: visible.length })}
          </span>
        </div>
        {canWrite && visible.length > 0 ? (
          <span className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" disabled={bulk} onClick={() => setAllVisible(true)}>
              {t("cap.enableVisible")}
            </Button>
            <Button variant="ghost" size="sm" disabled={bulk} onClick={() => setAllVisible(false)}>
              {t("cap.disableVisible")}
            </Button>
          </span>
        ) : null}
      </div>

      {data.sector === null ? (
        <p className="text-sm text-muted-foreground">{t("cap.sector.none")}</p>
      ) : viewingAll ? (
        <p className="text-sm text-muted-foreground">
          {t("cap.sector.viewingAll")}{" "}
          <a href={seeOwnHref} className="underline underline-offset-4">
            {t("cap.sector.seeOwn")}
          </a>
        </p>
      ) : data.hidden_by_sector > 0 ? (
        <p className="text-sm text-muted-foreground">
          {data.hidden_by_sector === 1
            ? t("cap.sector.hiddenOne")
            : t("cap.sector.hidden", { n: data.hidden_by_sector })}{" "}
          <a href={seeAllHref} className="underline underline-offset-4">
            {t("cap.sector.seeAll")}
          </a>
        </p>
      ) : null}

      {!canWrite ? <p className="text-sm text-muted-foreground">{t("cap.readonly")}</p> : null}

      {all.length === 0 ? (
        // Sin catálogo, las integraciones siguen arriba: hoy el vacío las
        // escondía y no había forma de conectar nada.
        <EmptyState icon={Wrench} title={t("cap.empty.title")} description={t("cap.empty.body")} readonly />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={Search}
          title={t("cap.noResults.title", { q })}
          description={t("cap.noResults.body")}
          action={
            <Button variant="outline" onClick={() => setQ("")}>
              {t("cap.sector.seeAll")}
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-(--space-section)">
          {groups.map((g) => (
            <Section key={g.fn} title={t(`cap.fn.${g.fn}`)} headingLevel={2} flat>
              <ul className="flex flex-col gap-2">
                {g.items.map((cap) => (
                  <CapabilityCard
                    key={`${cap.kind}:${cap.key}`}
                    refId={refId}
                    cap={cap}
                    canWrite={canWrite}
                    onChanged={() => router.refresh()}
                  />
                ))}
              </ul>
            </Section>
          ))}
        </div>
      )}
    </div>
  );
}
