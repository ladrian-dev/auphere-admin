"use client";

import * as React from "react";

import { Search } from "lucide-react";

import { ConfirmDialog, Button, Input } from "@nexus/ui";

import { reloadSectionAction } from "@/app/(console)/clients/[ref]/business/actions";
import { confirmSectionAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { languageName } from "@/components/clients/client-read-model";
import { BusinessLinks } from "@/components/business/sources/business-links";
import { BusinessSources } from "@/components/business/sources/business-sources";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Basics, Faqs, Hours, Locations, Policies, SectionState, SectorOption, Services, SpecialDates } from "@/lib/backend/business-sections";
import type { BusinessRecord, LinkItem, Section, Sources } from "@/lib/backend/client-records";

import { BasicsSection } from "./basics-section";
import { matchesText } from "./business-search";
import { FaqsSection } from "./faqs-section";
import { HoursSection } from "./hours-section";
import { BUSINESS_GRID, BUSINESS_INDEX_LIST, BUSINESS_SECTIONS_COLUMN } from "./layout";
import { LocationsSection } from "./locations-section";
import { PoliciesSection } from "./policies-section";
import { sectorSuggestion } from "./proposals-model";
import { reviewProgress } from "./review-model";
import { ReadLanguages, SectionEditProvider, SectionError, SectionFrame, SectionStateMark, type Result } from "./section-frame";
import { ServicesSection } from "./services-section";
import { SpecialDatesSection } from "./special-dates-section";

export type BusinessData = {
  basics: Result<Basics>;
  locations: Result<Locations>;
  hours: Result<Hours>;
  specialDates: Result<SpecialDates>;
  services: Result<Services>;
  /** «Políticas» y «Preguntas frecuentes» (enmienda del 2026-10-29, 60.4; sin ellas, no se pintan). */
  policies?: Result<Policies>;
  faqs?: Result<Faqs>;
  /** Los sectores con guía para el selector de Datos básicos (57.5). */
  sectors?: Result<SectorOption[]>;
  /** «Documentos y webs» y «Redes sociales» (sin ellas, no se pintan). */
  sources?: Result<Sources>;
  record?: Result<BusinessRecord>;
};

type Key = "basics" | "locations" | "hours" | "services" | "policies" | "faqs" | "sources" | "links";
type Reloadable = "basics" | "locations" | "hours" | "special_dates" | "services" | "policies" | "faqs";
const ORDER: readonly { key: Key; id: string; title: MessageKey; api?: Reloadable }[] = [
  { key: "basics", id: "business-basics", title: "business.basics.title", api: "basics" },
  { key: "locations", id: "business-locations", title: "business.locations.title", api: "locations" },
  { key: "hours", id: "business-hours", title: "business.hours.title", api: "hours" },
  { key: "services", id: "business-services", title: "business.services.title", api: "services" },
  { key: "policies", id: "business-policies", title: "business.policies.title", api: "policies" },
  { key: "faqs", id: "business-faqs", title: "business.faqs.title", api: "faqs" },
  { key: "sources", id: "business-sources", title: "business.docs.title" },
  { key: "links", id: "business-links", title: "business.socials.section" },
];

/**
 * Las redes guardadas, como las devuelve `GET /business` (`spec.links`). Ese
 * documento es portable y no lleva `id`, y cada enlace trae solo su `url` o su
 * `handle`; aquí el `id` es solo la clave de la fila.
 */
function linksOf(record: BusinessRecord): LinkItem[] {
  const raw = record.spec.links;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((l, i) => {
    if (typeof l !== "object" || l === null || typeof (l as LinkItem).network !== "string") return [];
    const { network, url, handle } = l as LinkItem;
    return [{ id: `saved-${i}`, network, url: url ?? null, handle: handle ?? null }];
  });
}

/**
 * La página Negocio de un cliente (spec 047, T060), como el prototipo aprobado
 * («Consola de partners v2»): un índice lateral con un círculo por sección
 * (requisito 8.5) y la nota de que todo lo heredan sus agentes, y seis
 * secciones en lectura con su «Editar» o «Añadir…». Una sola edición a la vez.
 * Las fechas especiales viven dentro de Horarios. Cada sección carga y falla
 * sola: si una no llega, lo dice y deja reintentar, y las demás siguen.
 *
 * Enmienda del 2026-10-29 (T209): «Políticas» y «Preguntas frecuentes» detrás
 * de Servicios, con lo sugerido por el sistema en su sección (60.4, 60.5), y
 * el sector en Datos básicos (57.5). Lo sugerido sale de las propuestas
 * pendientes de `GET /business`; si la ficha no se pudo leer, cada sección lo
 * dice y enseña lo escrito.
 */
/** Lo que se puede confirmar por sección (`POST /sections/{section}/confirm`). */
const CONFIRMABLE: ReadonlySet<Key> = new Set(["basics", "locations", "hours", "services", "policies", "faqs", "links"]);
type Versioned = "basics" | "locations" | "hours" | "services" | "policies" | "faqs";

export function BusinessSectionsView({
  refId,
  canWrite,
  data: initial,
  initialQuery = "",
}: {
  refId: string;
  canWrite: boolean;
  data: BusinessData;
  /** Spec 073 (4.1): lo buscado, de la URL (`?q=`). */
  initialQuery?: string;
}) {
  const t = useT();
  const locale = useLocale();
  const [data, setData] = React.useState(initial);
  // Spec 073 (4.1): el buscador. Vive en la URL (`?q=`) sin recargar la página.
  const [query, setQuery] = React.useState(initialQuery);
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (query.trim()) url.searchParams.set("q", query.trim());
    else url.searchParams.delete("q");
    window.history.replaceState(window.history.state, "", url);
  }, [query]);
  const [linksSaved, setLinksSaved] = React.useState<{ revision: number; filled: boolean } | null>(null);
  // Spec 055 (requisito 4): lo que cada sección avisó; va antes que la carga inicial.
  const [reported, setReported] = React.useState<Partial<Record<Key, SectionState>>>({});
  const reportState = React.useCallback(
    (key: Key) => (state: SectionState) => setReported((prev) => (prev[key] === state ? prev : { ...prev, [key]: state })),
    [],
  );
  // Spec 055: la moneda es de los dos, y cambiarla sube la revisión de los dos. La
  // sección que no la cambió se vuelve a leer y a montar, para no quedarse con lo viejo.
  const [versions, setVersions] = React.useState<Record<Versioned, number>>({ basics: 0, locations: 0, hours: 0, services: 0, policies: 0, faqs: 0 });
  const [, startTransition] = React.useTransition();
  function reloadAfterCurrency(key: "basics" | "services") {
    startTransition(async () => {
      const res = await reloadSectionAction({ ref: refId, section: key });
      if (!res?.ok) return;
      setData((prev) => ({ ...prev, [key]: res }));
      setVersions((prev) => ({ ...prev, [key]: prev[key] + 1 }));
    });
  }
  const locations = data.locations.ok ? data.locations.data.items : [];
  const record = data.record?.ok ? data.record.data : null;
  // Sin ficha no se sabe qué hay sugerido (`null`); con ella, sus propuestas pendientes.
  const suggestions = record ? record.suggestions : null;
  const stateIn = (section: Section): SectionState | null => record?.sections.find((x) => x.section === section)?.state ?? null;

  function retry(key: keyof BusinessData, api: Reloadable) {
    startTransition(async () => {
      const res = await reloadSectionAction({ ref: refId, section: api });
      if (res?.ok) setData((prev) => ({ ...prev, [key]: res }));
    });
  }

  const shown = ORDER.filter((item) =>
    item.key === "sources"
      ? data.sources !== undefined
      : item.key === "links"
        ? data.record !== undefined
        : item.key === "policies"
          ? data.policies !== undefined
          : item.key === "faqs"
            ? data.faqs !== undefined
            : true,
  );

  function stateOf(key: Key): SectionState | null {
    if (key === "sources") return data.sources?.ok ? (data.sources.data.items.length ? "complete" : "pending") : stateIn("sources");
    // Lo mismo que hace la API al guardar (`put_links`): con enlaces, completa.
    if (key === "links") return reported.links ?? (linksSaved ? (linksSaved.filled ? "complete" : "pending") : stateIn("links"));
    const entry = data[key];
    return entry?.ok ? (reported[key] ?? entry.data.state) : null;
  }

  // Spec 073 (4.5, D1): lo leído que queda por revisar. Se revisa por sección, como
  // la API; lo que ya se confirmó aquí (con «Es correcto» o «Marcar todo») cuenta
  // como revisado sin volver a leer la ficha.
  // Sin memo: depende del estado de cada sección (`stateOf`), y la cuenta es pequeña.
  const progress = (() => {
    const base = reviewProgress(record?.provenance ?? {});
    let reviewed = base.reviewed;
    const pending = { ...base.pending };
    for (const [section, n] of Object.entries(pending) as [Key, number][]) {
      // Revisión de staging: lo leído en una sección que ya no está «Leída» (completa,
      // pendiente…) no se puede confirmar desde aquí; cuenta como revisado, o la
      // barra no llegaría nunca al final.
      if (reported[section] === "complete" || stateOf(section) !== "read_pending") {
        reviewed += n;
        delete pending[section];
      }
    }
    return { pending, reviewed, total: base.total };
  })();
  // Spec 073 (4.6): en qué idioma se leyó cada sección, si no era el de la consola.
  const readIn = React.useMemo(() => {
    const out: Record<string, string> = {};
    for (const [pointer, p] of Object.entries(record?.provenance ?? {})) {
      if (!p.translated_from) continue;
      const item = ORDER.find((o) => {
        const prefix = o.key === "basics" ? "/business" : o.key === "sources" ? "/documents" : `/${o.key}`;
        return pointer === prefix || pointer.startsWith(`${prefix}/`);
      });
      if (item) out[item.id] = languageName(locale, p.translated_from);
    }
    return out;
  }, [record, locale]);
  const toMark = shown.filter((item) => CONFIRMABLE.has(item.key) && stateOf(item.key) === "read_pending").map((item) => item.key);
  const [asking, setAsking] = React.useState(false);
  const [marked, setMarked] = React.useState(false);

  async function markAll() {
    let failed = false;
    for (const key of toMark) {
      const res = await confirmSectionAction({ ref: refId, section: key as Section });
      if (!res.ok) {
        failed = true;
        continue;
      }
      setReported((prev) => ({ ...prev, [key]: "complete" }));
      if (key !== "links") {
        const k = key as Versioned;
        setData((prev) => {
          const entry = prev[k];
          return entry?.ok ? { ...prev, [k]: { ok: true, data: { ...entry.data, state: "complete" } } } : prev;
        });
        setVersions((prev) => ({ ...prev, [k]: prev[k] + 1 }));
      }
    }
    setAsking(false);
    setMarked(!failed);
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
        return data.basics.ok ? (
          <BasicsSection key={versions.basics} refId={refId} basics={data.basics.data} onPriceCurrencyChange={() => reloadAfterCurrency("services")} canWrite={canWrite} sectors={data.sectors} sectorProposal={sectorSuggestion(suggestions)} onStateChange={reportState("basics")} confirmable />
        ) : (
          failedFrame(item, () => retry("basics", "basics"))
        );
      case "locations":
        return data.locations.ok ? (
          <LocationsSection
            key={versions.locations}
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
          <HoursSection key={versions.hours} refId={refId} hours={data.hours.data} locations={locations} canWrite={canWrite} confirmable onStateChange={reportState("hours")}>
            {data.specialDates.ok ? (
              <SpecialDatesSection
                refId={refId}
                specialDates={data.specialDates.data}
                locations={locations}
                canWrite={canWrite}
                nested
                timezone={data.basics.ok ? data.basics.data.timezone : null}
              />
            ) : null}
          </HoursSection>
        ) : (
          failedFrame(item, () => retry("hours", "hours"))
        );
      case "services":
        return data.services.ok ? (
          <ServicesSection key={versions.services} refId={refId} services={data.services.data} onPriceCurrencyChange={() => reloadAfterCurrency("basics")} canWrite={canWrite} confirmable onStateChange={reportState("services")} query={query} />
        ) : (
          failedFrame(item, () => retry("services", "services"))
        );
      case "policies":
        return data.policies?.ok ? (
          <PoliciesSection key={versions.policies} refId={refId} policies={data.policies.data} suggestions={suggestions} canWrite={canWrite} onStateChange={reportState("policies")} confirmable />
        ) : (
          failedFrame(item, () => retry("policies", "policies"))
        );
      case "faqs":
        return data.faqs?.ok ? (
          <FaqsSection key={versions.faqs} refId={refId} faqs={data.faqs.data} suggestions={suggestions} canWrite={canWrite} onStateChange={reportState("faqs")} query={query} confirmable />
        ) : (
          failedFrame(item, () => retry("faqs", "faqs"))
        );
      case "sources":
        return (
          <SectionFrame id={item.id} title={t(item.title)} state={stateOf("sources")} canWrite={canWrite}>
            <BusinessSources refId={refId} initial={data.sources?.ok ? data.sources.data : null} canWrite={canWrite} bare />
          </SectionFrame>
        );
      case "links":
        return record ? (
          <SectionFrame
            id={item.id}
            title={t(item.title)}
            state={stateOf("links")}
            canWrite={canWrite}
            confirm={{ refId, section: "links", onConfirmed: () => setReported((prev) => ({ ...prev, links: "complete" })) }}
          >
            <BusinessLinks
              refId={refId}
              links={linksOf(record)}
              revision={linksSaved?.revision ?? record.sections.find((x) => x.section === "links")?.revision ?? 0}
              canWrite={canWrite}
              onSaved={(revision, links) => setLinksSaved({ revision, filled: links.length > 0 })}
              bare
            />
          </SectionFrame>
        ) : (
          failedFrame(item)
        );
    }
  }

  const searching = query.trim() !== "";
  const foundServices = data.services.ok ? data.services.data.items.filter((x) => !x.archived && matchesText(query, x.name, x.description, x.category)).length : 0;
  const foundFaqs = data.faqs?.ok ? data.faqs.data.items.filter((f) => !f.suggested && matchesText(query, f.q, f.a)).length : 0;
  const found = [
    t(foundServices === 1 ? "business.search.services.one" : "business.search.services.other", { n: foundServices }),
    ...(data.faqs !== undefined ? [t(foundFaqs === 1 ? "business.search.faqs.one" : "business.search.faqs.other", { n: foundFaqs })] : []),
  ].join(` ${t("business.search.and")} `);

  return (
    <SectionEditProvider>
      <ReadLanguages.Provider value={readIn}>
      <div className="grid min-w-0 gap-3" data-slot="business-top">
        <div className="relative min-w-0 max-w-md">
          <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input type="search" aria-label={t("business.search.label")} placeholder={t("business.search.placeholder")} value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" />
        </div>
        <p role="status" aria-label={t("business.search.results")} className="min-h-0 text-sm text-muted-foreground empty:hidden">
          {searching ? found : ""}
        </p>
        {progress.total > 0 ? (
          <div role="status" aria-label={t("business.review.label")} className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-card px-4 py-3" data-slot="business-review">
            <div className="grid min-w-0 flex-1 basis-56 gap-2">
              <span className="text-sm font-medium tabular-nums">{t("business.review.progress", { reviewed: progress.reviewed, total: progress.total })}</span>
              <span className="block h-2 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round((progress.reviewed / progress.total) * 100)}%` }} />
              </span>
              {marked && !toMark.length ? <span className="text-xs text-muted-foreground">{t("business.review.done")}</span> : null}
            </div>
            {canWrite && toMark.length ? (
              <Button type="button" size="sm" variant="outline" onClick={() => setAsking(true)}>
                {t("business.review.markAll")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={t("business.review.markAll")}
        description={t(toMark.length === 1 ? "business.review.markAll.body.one" : "business.review.markAll.body.other", { n: toMark.length })}
        confirmLabel={t("business.review.markAll.confirm")}
        cancelLabel={t("business.section.cancel")}
        onConfirm={markAll}
      />
      <div className={BUSINESS_GRID}>
        <div className="grid min-w-0 gap-3 lg:sticky lg:top-20">
          <nav aria-label={t("business.page.index")} className="min-w-0">
            {/* `relative`: el estado `sr-only` de cada sección es absoluto y, sin
                un contenedor posicionado, ensancha la página a 375 px. */}
            <ul className={BUSINESS_INDEX_LIST} data-scroll-x>
              {shown.map((item) => {
                const state = stateOf(item.key);
                return (
                  <li key={item.id} className="shrink-0">
                    <a
                      href={`#${item.id}`}
                      className="flex h-9 min-w-0 items-center justify-between gap-3 rounded-md px-3 text-sm transition-colors duration-(--duration-hover) hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      <span className="min-w-0 truncate">{t(item.title)}</span>
                      {state ? <SectionStateMark state={state} count={progress.pending[item.key as Section] ?? 0} /> : null}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
          <p className="hidden px-3 text-xs text-pretty text-muted-foreground lg:block">{t("business.page.note")}</p>
        </div>
        <div className={BUSINESS_SECTIONS_COLUMN}>
          {/* The client's name is the page's h1 (the client frame); the sections are h2. */}
          {shown.map((item) => (
            <React.Fragment key={item.id}>{body(item)}</React.Fragment>
          ))}
        </div>
      </div>
      </ReadLanguages.Provider>
    </SectionEditProvider>
  );
}
