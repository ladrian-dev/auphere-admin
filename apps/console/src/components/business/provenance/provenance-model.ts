import type { MessageKey } from "@/i18n/messages";
import type { Provenance, Section } from "@/lib/backend/client-records";

/**
 * Spec 047 (T069, requisito 13.1) — de dónde viene un dato de la ficha, en
 * palabras: «Escrito por ti», «Leído de la web · revísalo», «Migrado ·
 * revísalo», «Sugerido · confírmalo», «Editado por Marta desde la app».
 * La API manda la procedencia; aquí solo se elige la frase.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const READ = new Set(["web", "document", "social", "migrated"]);

export function provenanceText(t: T, p: Provenance, meId: string | null): string {
  if (p.source === "person") {
    if (p.by?.id && meId && p.by.id === meId) return t("business.prov.self");
    const name = p.by?.name ?? t("business.prov.someone");
    if (p.origin === "app") return t("business.prov.app", { name });
    if (p.origin === "lite_web") return t("business.prov.lite_web", { name });
    return t("business.prov.person", { name });
  }
  if (READ.has(p.source)) {
    return t(`business.prov.${p.source}${p.review === "pending" ? "" : ".ok"}` as MessageKey);
  }
  return t(`business.prov.${p.source}` as MessageKey);
}

/** ¿Está pendiente de que una persona lo revise? */
export function needsReview(p: Provenance | undefined): boolean {
  return p?.review === "pending";
}

/** El prefijo de los punteros de cada sección en el ClientSpec. */
const PREFIX: Record<Section, string> = {
  basics: "/business",
  locations: "/locations",
  hours: "/hours",
  special_dates: "/special_dates",
  services: "/services",
  policies: "/policies",
  faqs: "/faqs",
  sources: "/documents",
  links: "/links",
};

/** La procedencia que manda en una sección: la más reciente de sus datos. */
export function sectionProvenance(all: Record<string, Provenance>, section: Section): Provenance | null {
  const prefix = PREFIX[section];
  let best: Provenance | null = null;
  for (const [pointer, p] of Object.entries(all)) {
    if (pointer !== prefix && !pointer.startsWith(`${prefix}/`)) continue;
    if (!best || p.at > best.at) best = p;
  }
  return best;
}

/** ¿Queda en la sección algo leído sin revisar? (para «Es correcto»). */
export function sectionNeedsReview(all: Record<string, Provenance>, section: Section): boolean {
  const prefix = PREFIX[section];
  return Object.entries(all).some(([pointer, p]) => (pointer === prefix || pointer.startsWith(`${prefix}/`)) && p.review === "pending");
}
