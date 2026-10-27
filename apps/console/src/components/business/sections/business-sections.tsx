"use client";

import * as React from "react";

import { reloadSectionAction } from "@/app/(console)/clients/[ref]/business/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Basics, Hours, Locations, SectionState, Services, SpecialDates } from "@/lib/backend/business-sections";

import { BasicsSection } from "./basics-section";
import { HoursSection } from "./hours-section";
import { LocationsSection } from "./locations-section";
import { SectionError, SectionFrame, SectionStateBadge, type Result } from "./section-frame";
import { ServicesSection } from "./services-section";
import { SpecialDatesSection } from "./special-dates-section";

export type BusinessData = {
  basics: Result<Basics>;
  locations: Result<Locations>;
  hours: Result<Hours>;
  specialDates: Result<SpecialDates>;
  services: Result<Services>;
};

type Key = keyof BusinessData;
const ORDER: readonly { key: Key; id: string; title: MessageKey; api: "basics" | "locations" | "hours" | "special_dates" | "services" }[] = [
  { key: "basics", id: "business-basics", title: "business.basics.title", api: "basics" },
  { key: "locations", id: "business-locations", title: "business.locations.title", api: "locations" },
  { key: "hours", id: "business-hours", title: "business.hours.title", api: "hours" },
  { key: "specialDates", id: "business-special-dates", title: "business.special.title", api: "special_dates" },
  { key: "services", id: "business-services", title: "business.services.title", api: "services" },
];

/**
 * La página Negocio de un cliente (spec 047, T060): un índice lateral con el
 * estado de cada sección (requisito 8.5) y las secciones que escribe la
 * persona. Cada sección carga y falla sola: si una no llega, lo dice y deja
 * reintentar, y las demás siguen (el estado «parcial»).
 */
export function BusinessSectionsView({ refId, canWrite, data: initial }: { refId: string; canWrite: boolean; data: BusinessData }) {
  const t = useT();
  const [data, setData] = React.useState(initial);
  const [, startTransition] = React.useTransition();
  const locations = data.locations.ok ? data.locations.data.items : [];

  function retry(key: Key, api: (typeof ORDER)[number]["api"]) {
    startTransition(async () => {
      const res = await reloadSectionAction({ ref: refId, section: api });
      if (res?.ok) setData((prev) => ({ ...prev, [key]: res }));
    });
  }

  function stateOf(key: Key): SectionState | null {
    const entry = data[key];
    return entry.ok ? entry.data.state : null;
  }

  function body(item: (typeof ORDER)[number]) {
    const entry = data[item.key];
    if (!entry.ok) {
      return (
        <SectionFrame id={item.id} title={t(item.title)} canWrite={canWrite}>
          <SectionError onRetry={() => retry(item.key, item.api)} />
        </SectionFrame>
      );
    }
    switch (item.key) {
      case "basics":
        return <BasicsSection refId={refId} basics={entry.data as Basics} canWrite={canWrite} />;
      case "locations":
        return (
          <LocationsSection
            refId={refId}
            locations={entry.data as Locations}
            canWrite={canWrite}
            onChange={(next) => setData((prev) => ({ ...prev, locations: { ok: true, data: next } }))}
          />
        );
      case "hours":
        return <HoursSection refId={refId} hours={entry.data as Hours} locations={locations} canWrite={canWrite} />;
      case "specialDates":
        return <SpecialDatesSection refId={refId} specialDates={entry.data as SpecialDates} locations={locations} canWrite={canWrite} />;
      case "services":
        return <ServicesSection refId={refId} services={entry.data as Services} canWrite={canWrite} />;
    }
  }

  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-[13rem_minmax(0,1fr)] lg:items-start">
      <nav aria-label={t("business.page.index")} className="min-w-0 lg:sticky lg:top-20">
        <ul className="flex min-w-0 gap-2 overflow-x-auto pb-1 lg:grid lg:overflow-visible" data-scroll-x>
          {ORDER.map((item) => {
            const state = stateOf(item.key);
            return (
              <li key={item.id} className="shrink-0">
                <a
                  href={`#${item.id}`}
                  className="flex min-h-9 min-w-0 items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  <span className="min-w-0 truncate">{t(item.title)}</span>
                  {state ? (
                    <span className="sr-only lg:not-sr-only">
                      <SectionStateBadge state={state} />
                    </span>
                  ) : null}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="grid min-w-0 gap-6">
        {/* The client's name is the page's h1 (the client frame); the sections are h2. */}
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("business.page.intro")}</p>
        {ORDER.map((item) => (
          <React.Fragment key={item.id}>{body(item)}</React.Fragment>
        ))}
      </div>
    </div>
  );
}
