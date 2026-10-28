"use client";

import * as React from "react";

import { reloadSectionAction } from "@/app/(console)/clients/[ref]/business/actions";
import { BusinessLinks } from "@/components/business/sources/business-links";
import { BusinessSources } from "@/components/business/sources/business-sources";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Basics, Hours, Locations, SectionState, Services, SpecialDates } from "@/lib/backend/business-sections";
import type { BusinessRecord, LinkItem, Section, Sources } from "@/lib/backend/client-records";

import { BasicsSection } from "./basics-section";
import { HoursSection } from "./hours-section";
import { LocationsSection } from "./locations-section";
import { SectionEditProvider, SectionError, SectionFrame, SectionStateMark, type Result } from "./section-frame";
import { ServicesSection } from "./services-section";
import { SpecialDatesSection } from "./special-dates-section";

export type BusinessData = {
  basics: Result<Basics>;
  locations: Result<Locations>;
  hours: Result<Hours>;
  specialDates: Result<SpecialDates>;
  services: Result<Services>;
  /** «Documentos y webs» y «Redes sociales» (sin ellas, no se pintan). */
  sources?: Result<Sources>;
  record?: Result<BusinessRecord>;
};

type Key = "basics" | "locations" | "hours" | "services" | "sources" | "links";
type Reloadable = "basics" | "locations" | "hours" | "special_dates" | "services";
const ORDER: readonly { key: Key; id: string; title: MessageKey; api?: Reloadable }[] = [
  { key: "basics", id: "business-basics", title: "business.basics.title", api: "basics" },
  { key: "locations", id: "business-locations", title: "business.locations.title", api: "locations" },
  { key: "hours", id: "business-hours", title: "business.hours.title", api: "hours" },
  { key: "services", id: "business-services", title: "business.services.title", api: "services" },
  { key: "sources", id: "business-sources", title: "business.docs.title" },
  { key: "links", id: "business-links", title: "business.socials.section" },
];

/** Las redes guardadas, como las devuelve `GET /business` (`spec.links`). */
function linksOf(record: BusinessRecord): LinkItem[] {
  const raw = record.spec.links;
  if (!Array.isArray(raw)) return [];
  return raw.filter((l): l is LinkItem => typeof l === "object" && l !== null && typeof (l as LinkItem).id === "string" && typeof (l as LinkItem).network === "string");
}

/**
 * La página Negocio de un cliente (spec 047, T060), como el prototipo aprobado
 * («Consola de partners v2»): un índice lateral con un círculo por sección
 * (requisito 8.5) y la nota de que todo lo heredan sus agentes, y seis
 * secciones en lectura con su «Editar» o «Añadir…». Una sola edición a la vez.
 * Las fechas especiales viven dentro de Horarios. Cada sección carga y falla
 * sola: si una no llega, lo dice y deja reintentar, y las demás siguen.
 */
export function BusinessSectionsView({ refId, canWrite, data: initial }: { refId: string; canWrite: boolean; data: BusinessData }) {
  const t = useT();
  const [data, setData] = React.useState(initial);
  const [linksRevision, setLinksRevision] = React.useState<number | null>(null);
  const [, startTransition] = React.useTransition();
  const locations = data.locations.ok ? data.locations.data.items : [];
  const record = data.record?.ok ? data.record.data : null;
  const stateIn = (section: Section): SectionState | null => record?.sections.find((x) => x.section === section)?.state ?? null;

  function retry(key: keyof BusinessData, api: Reloadable) {
    startTransition(async () => {
      const res = await reloadSectionAction({ ref: refId, section: api });
      if (res?.ok) setData((prev) => ({ ...prev, [key]: res }));
    });
  }

  const shown = ORDER.filter((item) => (item.key === "sources" ? data.sources !== undefined : item.key === "links" ? data.record !== undefined : true));

  function stateOf(key: Key): SectionState | null {
    if (key === "sources") return data.sources?.ok ? (data.sources.data.items.length ? "complete" : "pending") : stateIn("sources");
    if (key === "links") return stateIn("links");
    const entry = data[key];
    return entry.ok ? entry.data.state : null;
  }

  function failedFrame(item: (typeof ORDER)[number], onRetry?: () => void) {
    return (
      <SectionFrame id={item.id} title={t(item.title)} canWrite={canWrite}>
        <SectionError onRetry={onRetry} />
      </SectionFrame>
    );
  }

  function body(item: (typeof ORDER)[number]) {
    switch (item.key) {
      case "basics":
        return data.basics.ok ? <BasicsSection refId={refId} basics={data.basics.data} canWrite={canWrite} /> : failedFrame(item, () => retry("basics", "basics"));
      case "locations":
        return data.locations.ok ? (
          <LocationsSection
            refId={refId}
            locations={data.locations.data}
            canWrite={canWrite}
            confirmable
            onChange={(next) => setData((prev) => ({ ...prev, locations: { ok: true, data: next } }))}
          />
        ) : (
          failedFrame(item, () => retry("locations", "locations"))
        );
      case "hours":
        return data.hours.ok ? (
          <HoursSection refId={refId} hours={data.hours.data} locations={locations} canWrite={canWrite} confirmable>
            {data.specialDates.ok ? (
              <SpecialDatesSection refId={refId} specialDates={data.specialDates.data} locations={locations} canWrite={canWrite} nested />
            ) : null}
          </HoursSection>
        ) : (
          failedFrame(item, () => retry("hours", "hours"))
        );
      case "services":
        return data.services.ok ? (
          <ServicesSection refId={refId} services={data.services.data} canWrite={canWrite} confirmable />
        ) : (
          failedFrame(item, () => retry("services", "services"))
        );
      case "sources":
        return (
          <SectionFrame id={item.id} title={t(item.title)} state={stateOf("sources")} canWrite={canWrite}>
            <BusinessSources refId={refId} initial={data.sources?.ok ? data.sources.data : null} canWrite={canWrite} bare />
          </SectionFrame>
        );
      case "links":
        return record ? (
          <SectionFrame id={item.id} title={t(item.title)} state={stateOf("links")} canWrite={canWrite}>
            <BusinessLinks
              refId={refId}
              links={linksOf(record)}
              revision={linksRevision ?? record.sections.find((x) => x.section === "links")?.revision ?? 0}
              canWrite={canWrite}
              onSaved={setLinksRevision}
              bare
            />
          </SectionFrame>
        ) : (
          failedFrame(item)
        );
    }
  }

  return (
    <SectionEditProvider>
      <div className="grid min-w-0 gap-6 lg:grid-cols-[12.5rem_minmax(0,1fr)] lg:items-start">
        <div className="grid min-w-0 gap-3 lg:sticky lg:top-20">
          <nav aria-label={t("business.page.index")} className="min-w-0">
            {/* `relative`: el estado `sr-only` de cada sección es absoluto y, sin
                un contenedor posicionado, ensancha la página a 375 px. */}
            <ul className="relative flex min-w-0 gap-1 overflow-x-auto pb-1 lg:grid lg:overflow-visible lg:pb-0" data-scroll-x>
              {shown.map((item) => {
                const state = stateOf(item.key);
                return (
                  <li key={item.id} className="shrink-0">
                    <a
                      href={`#${item.id}`}
                      className="flex h-9 min-w-0 items-center justify-between gap-3 rounded-md px-3 text-sm transition-colors duration-(--duration-hover) hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      <span className="min-w-0 truncate">{t(item.title)}</span>
                      {state ? <SectionStateMark state={state} /> : null}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
          <p className="hidden px-3 text-xs text-pretty text-muted-foreground lg:block">{t("business.page.note")}</p>
        </div>
        <div className="grid min-w-0 gap-4">
          {/* The client's name is the page's h1 (the client frame); the sections are h2. */}
          {shown.map((item) => (
            <React.Fragment key={item.id}>{body(item)}</React.Fragment>
          ))}
        </div>
      </div>
    </SectionEditProvider>
  );
}
