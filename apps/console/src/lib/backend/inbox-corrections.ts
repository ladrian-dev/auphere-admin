import type { Call } from "../backend";

/**
 * Spec 047 (T176; requisitos 52.1 a 52.6; `contracts/lite-app-api.md` §3) —
 * «Corregir esta respuesta» desde la Bandeja de la persona del cliente.
 *
 * El borrador dice de qué tipo es (`data` se aplica al momento, `behavior` llega
 * al partner como propuesta) y dónde hay datos de un cliente final (`pii`: el
 * campo, el tipo y sus posiciones, nunca el dato). Editar y enviar mandan
 * `If-Match` con su `revision`. Las respuestas no repiten el mensaje del
 * cliente: llevan la lección, que escribió la persona, y la paráfrasis.
 */
export type CorrectionScope = "business" | "agent";
export type CorrectionKind = "data" | "behavior";
export type CorrectionPiiKind = "email" | "document" | "phone" | "name";
export type CorrectionPii = { field: "lesson" | "paraphrase"; kind: CorrectionPiiKind | string; start: number; end: number };
export type CorrectionStatus = "draft" | "applied" | "proposed" | "undone" | "accepted" | "rejected";

export type Correction = {
  id: string;
  revision: number;
  status: CorrectionStatus | string;
  kind: CorrectionKind;
  scope: CorrectionScope;
  lesson: string;
  paraphrase: string | null;
  pii: CorrectionPii[];
  agent: { id: string; name: string };
  applied_change_id: string | null;
  proposal_id: string | null;
  created_at: string;
  sent_at: string | null;
  undone_at: string | null;
};

/** Los límites de la API (`inbox_correction.LESSON_MAX`, `PARAPHRASE_MAX` y `RULE_MAX`). */
export const CORRECTION_LIMITS = { lesson: 2000, paraphrase: 300, rule: 300 } as const;

export function inboxCorrectionsApi(call: Call) {
  const enc = encodeURIComponent;
  const ifMatch = (revision: number) => ({ "If-Match": `"${revision}"` });
  return {
    createCorrection: (conversationId: string, messageId: string, body: { text: string; scope: CorrectionScope }, key?: string) =>
      call<Correction>(`/console/lite/inbox/${enc(conversationId)}/messages/${enc(messageId)}/corrections`, {
        method: "POST",
        body,
        ...(key ? { headers: { "Idempotency-Key": key } } : {}),
      }),
    editCorrection: (id: string, revision: number, body: { lesson?: string; paraphrase?: string }) =>
      call<Correction>(`/console/lite/corrections/${enc(id)}`, { method: "PATCH", body, headers: ifMatch(revision) }),
    sendCorrection: (id: string, revision: number) =>
      call<Correction>(`/console/lite/corrections/${enc(id)}/send`, { method: "POST", headers: ifMatch(revision) }),
    undoCorrection: (id: string) => call<Correction>(`/console/lite/corrections/${enc(id)}/undo`, { method: "POST" }),
  };
}
