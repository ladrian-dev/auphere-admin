import type { MessageKey } from "@/i18n/messages";
import { TEACH_MAX_CHARS, type KnowledgeSource, type TeachScope } from "@/lib/backend/agent-knowledge-types";

import { undoOpen } from "./quality-model";

/**
 * Spec 047 (historia 22, T134) — el conocimiento de un agente sin pintar nada:
 * qué fuentes se ven (las vivas y las quitadas que aún se pueden recuperar),
 * cómo se llama cada tipo y qué falta para poder «Enseñar» (37.3: el alcance
 * siempre lo elige la persona).
 */

/** Las vivas, en el orden de la API, y las quitadas que aún se pueden recuperar (12.2). */
export function visibleSources(items: readonly KnowledgeSource[], now: number = Date.now()): { live: KnowledgeSource[]; restorable: KnowledgeSource[] } {
  const live: KnowledgeSource[] = [];
  const restorable: KnowledgeSource[] = [];
  for (const doc of items) {
    if (!doc.removed_at) live.push(doc);
    else if (undoOpen(doc.restore_until, now)) restorable.push(doc);
  }
  return { live, restorable };
}

const KINDS = new Set(["file", "url", "note"]);
export function sourceKindKey(kind: string): MessageKey {
  return (KINDS.has(kind) ? `builder.knowledge.kind.${kind}` : "builder.knowledge.kind.file") as MessageKey;
}

/** «Además sabe N fuentes del negocio». */
export function businessLineKey(n: number): MessageKey {
  return n <= 0 ? "builder.knowledge.business.none" : n === 1 ? "builder.knowledge.business.one" : "builder.knowledge.business.other";
}

/** Una web pública: `http(s)://` y algo detrás. La API vuelve a mirar el resto. */
export function isWebAddress(value: string): boolean {
  return /^https?:\/\/\S{3,}$/i.test(value.trim());
}

/** Lo que impide «Enseñar», en el orden en que se lee el formulario; `null` si nada. */
export function teachProblem(text: string, scope: TeachScope | null): MessageKey | null {
  const clean = text.trim();
  if (!clean) return "builder.teach.required.text";
  if (clean.length > TEACH_MAX_CHARS) return "builder.teach.tooLong";
  if (!scope) return "builder.teach.required.scope";
  return null;
}

/** Qué pruebas se vuelven a pasar, dicho según el alcance elegido. */
export function retestKey(scope: TeachScope | null): MessageKey {
  return scope === "agent" ? "builder.teach.retest.agent" : scope === "business" ? "builder.teach.retest.business" : "builder.teach.retest.none";
}

/** Negocio › Documentos y webs: la capa del negocio, que se gestiona allí. */
export function businessKnowledgeHref(refId: string): string {
  return `/clients/${encodeURIComponent(refId)}/knowledge`;
}

/** «14:32»: hasta cuándo se puede deshacer. */
export function formatClock(iso: string | null | undefined, locale: "es" | "en"): string {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, { timeStyle: "short" }).format(d);
}
