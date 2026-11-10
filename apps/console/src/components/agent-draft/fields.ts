import type { MessageKey } from "@/i18n/messages";
import type { DraftChange } from "@/lib/backend/agent-draft-types";

/**
 * Spec 047 (historia 2): the API names what changed in stable keys
 * (`system_prompt`, `settings.tone`, `audience`…) and the console turns them
 * into words. A key without a word of its own is «Otros ajustes»: platform
 * keys a partner does not edit here, said once.
 */
const LABEL: Record<string, MessageKey> = {
  system_prompt: "agents.draft.field.system_prompt",
  tools: "agents.draft.field.tools",
  skills: "agents.draft.field.skills",
  "settings.identity": "agents.draft.field.identity",
  "settings.tone": "agents.draft.field.tone",
  "settings.objective": "agents.draft.field.objective",
  "settings.schedule": "agents.draft.field.schedule",
  "settings.languages": "agents.draft.field.languages",
  "settings.escalation": "agents.draft.field.escalation",
  "settings.ai_disclosure": "agents.draft.field.ai_disclosure",
  audience: "agents.draft.field.audience",
  payment_review: "agents.draft.field.payment_review",
};

export function fieldLabelKey(field: string): MessageKey {
  return LABEL[field] ?? "agents.draft.field.other";
}

/** The words for `fields`, each once, in the order they came. */
export function fieldLabels(fields: readonly string[], t: (key: MessageKey) => string): string[] {
  return [...new Set(fields.map((f) => t(fieldLabelKey(f))))];
}

/** «Tono», «Tono y Horario», «Tono, Horario y Objetivo». */
export function joinList(items: readonly string[], and: string): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} ${and} ${items[items.length - 1]}`;
}

/** The fields both people changed: where saving mine replaces theirs. */
export function overlap(theirs: readonly string[], mine: readonly string[]): string[] {
  const wanted = new Set(mine);
  return [...new Set(theirs.filter((f) => wanted.has(f)))];
}

/** Every field the other writes touched, each once. */
export function theirFields(changes: readonly DraftChange[]): string[] {
  return [...new Set(changes.flatMap((c) => c.fields))];
}

/** Who wrote after me, each once, in order. */
export function authorsOf(changes: readonly DraftChange[]): string[] {
  return [...new Set(changes.map((c) => c.by))];
}

/**
 * The title of the notice: «Hay cambios más nuevos de Luis» — unless the last
 * thing that happened was publishing or discarding the draft, which says it.
 */
export function conflictTitle(changes: readonly DraftChange[]): { key: MessageKey; who: string[] } {
  const last = changes[changes.length - 1];
  if (!last) return { key: "agents.draft.conflict.titleSomeone", who: [] };
  if (last.kind === "publish") return { key: "agents.draft.conflict.titlePublished", who: [last.by] };
  if (last.kind === "discard") return { key: "agents.draft.conflict.titleDiscarded", who: [last.by] };
  return { key: "agents.draft.conflict.title", who: authorsOf(changes) };
}
