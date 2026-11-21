import type { Provenance, ProvenanceSource, Section } from "@/lib/backend/client-records";

/**
 * Spec 073 (4.5, D1): cuánto de lo leído falta por revisar, por sección y en total.
 * Puro. Se revisa por sección (`POST /sections/{section}/confirm`), como la API; la
 * barra cuenta datos para que se vea cuánto queda.
 *
 * Solo cuenta lo **leído** (la web, un documento, las redes): lo que escribió una
 * persona ya es suyo y no hay nada que revisar.
 */
const READ: ReadonlySet<ProvenanceSource> = new Set(["web", "document", "social"]);

/** El prefijo de los punteros de cada sección en el ClientSpec (el de `provenance-model`). */
const PREFIX: readonly [Section, string][] = [
  ["basics", "/business"],
  ["locations", "/locations"],
  ["hours", "/hours"],
  ["special_dates", "/special_dates"],
  ["services", "/services"],
  ["policies", "/policies"],
  ["faqs", "/faqs"],
  ["sources", "/documents"],
  ["links", "/links"],
];

function sectionOf(pointer: string): Section | null {
  for (const [section, prefix] of PREFIX) if (pointer === prefix || pointer.startsWith(`${prefix}/`)) return section;
  return null;
}

export type ReviewProgress = {
  /** Lo leído sin revisar, por sección (solo las que tienen algo). */
  pending: Partial<Record<Section, number>>;
  reviewed: number;
  total: number;
};

export function reviewProgress(provenance: Record<string, Provenance>): ReviewProgress {
  const pending: Partial<Record<Section, number>> = {};
  let reviewed = 0;
  let total = 0;
  for (const [pointer, p] of Object.entries(provenance)) {
    if (!READ.has(p.source)) continue;
    const section = sectionOf(pointer);
    if (!section) continue;
    total += 1;
    if (p.review === "pending") pending[section] = (pending[section] ?? 0) + 1;
    else reviewed += 1;
  }
  return { pending, reviewed, total };
}
