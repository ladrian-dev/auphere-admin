import type { MessageKey } from "@/i18n/messages";
import { POLICY_KEYS, type PolicyKey } from "@/lib/backend/business-sections";
import type { ProvenanceSource, Suggestion } from "@/lib/backend/client-records";

/**
 * Spec 047, enmienda del 2026-10-29 (T209; requisitos 57.3, 60.4 y 60.5) — qué
 * propuesta pendiente de `GET /business` va a cada sitio de Negocio, sin pintar
 * nada. Las del sistema (el constructor del cliente, la lectura, una
 * importación) llegan como sugerencias con su puntero: `/policies/{clave}`,
 * `/faqs/-` y, para el sector, `/business/sector` (`contracts/console-api.md` §10).
 */

export const SECTOR_POINTER = "/business/sector";

function policyKeyOf(pointer: string): PolicyKey | null {
  const m = /^\/policies\/([a-z_]+)$/.exec(pointer);
  return m && (POLICY_KEYS as readonly string[]).includes(m[1]!) ? (m[1] as PolicyKey) : null;
}

/** Las propuestas de cada política, por su clave. */
export function policySuggestions(suggestions: readonly Suggestion[]): Map<PolicyKey, Suggestion[]> {
  const out = new Map<PolicyKey, Suggestion[]>();
  for (const s of suggestions) {
    const key = policyKeyOf(s.pointer);
    if (!key) continue;
    out.set(key, [...(out.get(key) ?? []), s]);
  }
  return out;
}

/** Las preguntas propuestas (`/faqs/-`, una nueva cada una). */
export function faqSuggestions(suggestions: readonly Suggestion[]): Suggestion[] {
  return suggestions.filter((s) => s.pointer === "/faqs/-" || (s.section === "faqs" && s.pointer.startsWith("/faqs/")));
}

/** La propuesta del sistema contra un sector fijado por una persona (57.3), si la hay. */
export function sectorSuggestion(suggestions: readonly Suggestion[] | null): Suggestion | null {
  return suggestions?.find((s) => s.pointer === SECTOR_POINTER) ?? null;
}

export type FaqValue = { q: string; a: string };

export function asFaq(value: unknown): FaqValue | null {
  if (value && typeof value === "object" && "q" in value && "a" in value) {
    const v = value as { q: unknown; a: unknown };
    return { q: String(v.q ?? ""), a: String(v.a ?? "") };
  }
  return null;
}

export function asText(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : JSON.stringify(value);
}

/** La etiqueta de un sector propuesto: `{key, label}` o, por si acaso, el texto. */
export function sectorLabelOf(value: unknown): string {
  if (value && typeof value === "object" && "label" in value) return String((value as { label: unknown }).label ?? "");
  return asText(value);
}

const SOURCES: ReadonlySet<ProvenanceSource> = new Set(["builder", "web", "document", "social", "import", "inbox_correction"]);

/** De dónde sale lo sugerido, dicho sin nombrar al constructor (60.5; Andrés, 2026-10-28). */
export function sourceKey(source: ProvenanceSource | null | undefined): MessageKey {
  return source && SOURCES.has(source) ? (`business.suggested.from.${source}` as MessageKey) : "business.suggested.from.other";
}
