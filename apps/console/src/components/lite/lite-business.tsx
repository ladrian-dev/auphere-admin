"use client";

import { History, Undo2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, PageHeader, formatRelative } from "@nexus/ui";

import {
  archiveLiteLocationAction,
  archiveLiteServiceAction,
  archiveLiteSpecialDateAction,
  createLiteLocationAction,
  createLiteServiceAction,
  createLiteSpecialDateAction,
  loadLiteHoursAction,
  reloadBusinessAction,
  saveLiteHoursAction,
  undoLiteChangeAction,
  updateLiteLocationAction,
  updateLiteServiceAction,
} from "@/app/(console)/negocio/actions";
import type { Result } from "@/components/builder/builder-model";
import { HoursSection } from "@/components/business/sections/hours-section";
import { LocationsSection, type LocationsActions } from "@/components/business/sections/locations-section";
import { ServicesSection, type ServicesActions } from "@/components/business/sections/services-section";
import { SpecialDatesSection, type SpecialDatesActions } from "@/components/business/sections/special-dates-section";
import { RowActions, type RowAction } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Hours, HoursBody, LocationBody, Locations, ServiceBody, Services, SpecialDateBody, SpecialDates } from "@/lib/backend/business-sections";
import type { LiteBusiness, LiteChange, LiteServiceNew, LiteServicePatch, LiteUndo } from "@/lib/backend/lite-agents";

import { idempotencyKey } from "./lite-agents-model";

type Keyed<B> = B & { key?: string };

export type LiteBusinessActions = {
  reload: () => Promise<Result<LiteBusiness>>;
  loadHours: (body: { location_id: string | null }) => Promise<Result<Hours>>;
  saveHours: (body: Keyed<{ revision: number; location_id: string | null; body: HoursBody }>) => Promise<Result<Hours>>;
  createSpecialDate: (body: Keyed<{ revision: number; body: SpecialDateBody }>) => Promise<Result<SpecialDates>>;
  archiveSpecialDate: (body: Keyed<{ revision: number; id: string }>) => Promise<Result<SpecialDates>>;
  createService: (body: Keyed<{ revision: number; body: LiteServiceNew }>) => Promise<Result<Services>>;
  updateService: (body: Keyed<{ revision: number; id: string; body: LiteServicePatch }>) => Promise<Result<Services>>;
  archiveService: (body: Keyed<{ revision: number; id: string }>) => Promise<Result<Services>>;
  createLocation: (body: Keyed<{ revision: number; body: LocationBody }>) => Promise<Result<Locations>>;
  updateLocation: (body: Keyed<{ revision: number; id: string; body: LocationBody }>) => Promise<Result<Locations>>;
  archiveLocation: (body: Keyed<{ revision: number; id: string; restore: boolean }>) => Promise<Result<Locations>>;
  undo: (body: Keyed<{ id: string }>) => Promise<Result<LiteUndo>>;
};

const SERVER_ACTIONS: LiteBusinessActions = {
  reload: () => reloadBusinessAction(),
  loadHours: (b) => loadLiteHoursAction(b),
  saveHours: (b) => saveLiteHoursAction(b),
  createSpecialDate: (b) => createLiteSpecialDateAction(b),
  archiveSpecialDate: (b) => archiveLiteSpecialDateAction(b),
  createService: (b) => createLiteServiceAction(b),
  updateService: (b) => updateLiteServiceAction(b),
  archiveService: (b) => archiveLiteServiceAction(b),
  createLocation: (b) => createLiteLocationAction(b),
  updateLocation: (b) => updateLiteLocationAction(b),
  archiveLocation: (b) => archiveLiteLocationAction(b),
  undo: (b) => undoLiteChangeAction(b),
};

const SECTION_LABEL: Record<string, MessageKey> = {
  hours: "business.hours.title",
  special_dates: "business.special.title",
  services: "business.services.title",
  locations: "business.locations.title",
};

/**
 * «Negocio» de la consola lite (spec 047, T168; requisitos 50.1, 50.2 y 50.4):
 * lo que el negocio sabe mejor que nadie —el horario con sus turnos, las fechas
 * especiales, los servicios con su precio y su duración, y las sedes— con las
 * mismas secciones que la ficha del partner y sus mismas reglas (revisión,
 * conflicto, frase «Así lo dirá el agente»). Cada cambio lleva el nombre de la
 * persona y «desde la web», avisa al partner y se puede deshacer en «Últimos
 * cambios». El agente lo usa desde el siguiente mensaje.
 *
 * Lo que es del partner no se pinta: los datos básicos, quién hace cada servicio
 * y qué agentes lo usan, duplicar y el nombre de un servicio que ya existe
 * (50.3). El horario es el del negocio o el de una sede (el suyo o el que hereda).
 */
export function LiteBusinessView({ initial, actions = SERVER_ACTIONS }: { initial: LiteBusiness | null; actions?: LiteBusinessActions }) {
  const t = useT();
  const [data, setData] = React.useState(initial);
  const [history, setHistory] = React.useState<LiteChange[]>(initial?.history ?? []);
  const [locations, setLocations] = React.useState(initial?.locations.items ?? []);
  // Sube al deshacer o al releer: las secciones vuelven a nacer con lo de ahora.
  const [version, setVersion] = React.useState(0);
  const [reloading, startReload] = React.useTransition();
  const live = locations.filter((l) => !l.archived);

  const reloadAll = React.useCallback(async (): Promise<boolean> => {
    const res = await actions.reload();
    if (!res.ok) return false;
    setData(res.data);
    setHistory(res.data.history);
    setLocations(res.data.locations.items);
    setVersion((v) => v + 1);
    return true;
  }, [actions]);

  const sections = React.useMemo(() => {
    // Después de cada escritura, el historial se lee otra vez (sin tocar lo que se está editando).
    async function after<T>(pending: Promise<Result<T>>): Promise<Result<T>> {
      const res = await pending;
      if (res.ok) {
        void actions.reload().then((r) => {
          if (r.ok) setHistory(r.data.history);
        });
      }
      return res;
    }
    const services: ServicesActions = {
      create: (b) => after(actions.createService({ revision: b.revision, body: { ...b.body, name: b.body.name ?? "" }, key: idempotencyKey() })),
      update: (b) => after(actions.updateService({ revision: b.revision, id: b.id, body: withoutName(b.body), key: idempotencyKey() })),
      archive: (b) => after(actions.archiveService({ revision: b.revision, id: b.id, key: idempotencyKey() })),
    };
    const special: SpecialDatesActions = {
      create: (b) => after(actions.createSpecialDate({ revision: b.revision, body: b.body, key: idempotencyKey() })),
      archive: (b) => after(actions.archiveSpecialDate({ revision: b.revision, id: b.id, key: idempotencyKey() })),
    };
    const places: LocationsActions = {
      create: (b) => after(actions.createLocation({ revision: b.revision, body: b.body, key: idempotencyKey() })),
      update: (b) => after(actions.updateLocation({ revision: b.revision, id: b.id, body: b.body, key: idempotencyKey() })),
      archive: (b) => after(actions.archiveLocation({ revision: b.revision, id: b.id, restore: b.restore, key: idempotencyKey() })),
    };
    const hours = {
      save: (b: { revision: number; locationId: string | null; body: HoursBody }) =>
        after(actions.saveHours({ revision: b.revision, location_id: b.locationId, body: b.body, key: idempotencyKey() })),
      load: (b: { locationId: string | null }) => actions.loadHours({ location_id: b.locationId }),
    };
    return { services, special, places, hours };
  }, [actions]);

  function retry() {
    startReload(async () => {
      if (!(await reloadAll())) toast.error(t("lite.business.error.load"));
    });
  }

  async function undo(change: LiteChange) {
    const res = await actions.undo({ id: change.id, key: idempotencyKey() });
    if (res.ok) {
      await reloadAll();
      toast.success(t("lite.business.undone"));
      return;
    }
    if (res.status === 412) toast.error(t("lite.business.undo.conflict"));
    else if (res.code === "already_undone") toast.error(t("lite.business.undo.already"));
    else if (res.code === "undo_not_available") toast.error(t("lite.business.undo.unavailable"));
    else toast.error(t("lite.business.error.generic"));
    await reloadAll();
  }

  if (!data) {
    return (
      <div className="grid min-w-0 gap-6" data-slot="lite-business">
        <PageHeader title={t("nav.business")} description={t("lite.business.intro")} />
        <ErrorState title={t("lite.business.error.load")} description={t("lite.business.error.load.hint")} onRetry={retry} retryLabel={t("lite.agents.retry")} />
      </div>
    );
  }

  return (
    <div className="grid min-w-0 gap-6" data-slot="lite-business" aria-busy={reloading}>
      <PageHeader title={t("nav.business")} description={t("lite.business.intro")} />
      <nav aria-label={t("lite.business.index")} className="min-w-0">
        <ul className="flex min-w-0 gap-2 overflow-x-auto pb-1" data-scroll-x>
          {[
            ["business-hours", "business.hours.title"],
            ["business-special-dates", "business.special.title"],
            ["business-services", "business.services.title"],
            ["business-locations", "business.locations.title"],
            ["business-history", "lite.business.history"],
          ].map(([id, label]) => (
            <li key={id} className="shrink-0">
              <a
                href={`#${id}`}
                className="inline-flex min-h-8 items-center rounded-full px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                {t(label as MessageKey)}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div key={version} className="grid min-w-0 gap-6">
        <HoursSection
          refId=""
          hours={data.hours}
          locations={live}
          canWrite={data.hours.allowed.includes("edit")}
          save={(b) => sections.hours.save(b)}
          load={(b) => sections.hours.load(b)}
        />
        <SpecialDatesSection refId="" specialDates={data.special_dates} locations={live} canWrite={data.special_dates.allowed.includes("edit")} actions={sections.special} />
        <ServicesSection refId="" services={data.services} canWrite={data.services.allowed.includes("edit")} actions={sections.services} renameable={false} />
        <LocationsSection
          refId=""
          locations={data.locations}
          canWrite={data.locations.allowed.includes("edit")}
          actions={sections.places}
          onChange={(next) => setLocations(next.items)}
        />
      </div>
      <ChangeHistory changes={history} onUndo={undo} />
    </div>
  );
}

function withoutName(body: ServiceBody): LiteServicePatch {
  const { name: _name, ...rest } = body;
  void _name;
  return rest;
}

/** «Últimos cambios»: quién, desde dónde y cuándo, con «Deshacer» en el último de cada sección (13.3). */
function ChangeHistory({ changes, onUndo }: { changes: LiteChange[]; onUndo: (change: LiteChange) => Promise<void> }) {
  const t = useT();
  const locale = useLocale();
  const [busy, setBusy] = React.useState<string | null>(null);
  const undoable = (c: LiteChange) => c.undoable && !c.undone_at;
  const menu = foldsIntoMenu(changes.filter(undoable).length);
  return (
    <section id="business-history" aria-labelledby="business-history-title" className="grid min-w-0 scroll-mt-24 gap-4 rounded-md border border-border bg-card p-4 sm:p-6">
      <div className="grid gap-1">
        <h2 id="business-history-title" className="flex items-center gap-2 text-base font-semibold">
          <History className="size-4" aria-hidden="true" />
          {t("lite.business.history")}
        </h2>
        <p className="text-sm text-pretty text-muted-foreground">{t("lite.business.history.intro")}</p>
      </div>
      {changes.length === 0 ? (
        <EmptyState title={t("lite.business.history.empty")} readonly />
      ) : (
        <ul aria-label={t("lite.business.history")} className="grid min-w-0 divide-y divide-border-soft">
          {changes.map((c) => {
            const what = c.kind === "correction" ? t("lite.business.change.correction") : t(SECTION_LABEL[c.section] ?? "lite.business.change.other");
            const who = c.by?.name ?? t(c.by?.kind === "client_user" ? "lite.business.by.team" : "lite.business.by.partner");
            const where = c.origin === "app" ? t("lite.business.origin.app") : c.origin === "lite_web" ? t("lite.business.origin.web") : "";
            const actions: RowAction[] = undoable(c)
              ? [
                  {
                    label: t("lite.business.undo"),
                    primary: true,
                    disabled: busy !== null,
                    onSelect: () => {
                      setBusy(c.id);
                      void onUndo(c).finally(() => setBusy(null));
                    },
                  },
                ]
              : [];
            return (
              <li key={c.id} className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-2">
                <div className="grid min-w-0 gap-1">
                  <span className="text-sm font-medium text-pretty">{what}</span>
                  <span className="text-xs text-pretty text-muted-foreground">
                    {[who, where, formatRelative(c.at, locale)].filter(Boolean).join(" · ")}
                    {c.undone_at ? ` · ${t("lite.business.undone.mark")}` : ""}
                  </span>
                </div>
                {actions.length ? (
                  menu ? (
                    <RowActions actions={actions} menu ariaLabel={t("lite.business.change.actions", { what })} />
                  ) : (
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={actions[0]?.onSelect}
                      aria-label={t("lite.business.undo.of", { what })}
                      className="inline-flex min-h-8 items-center gap-1 rounded-sm px-2 text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
                    >
                      <Undo2 className="size-4" aria-hidden="true" />
                      {t("lite.business.undo")}
                    </button>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
