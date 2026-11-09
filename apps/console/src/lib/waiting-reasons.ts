import type { MessageKey } from "@/i18n/messages";

/**
 * Por qué una conversación espera a una persona, en palabras — spec 047
 * (`contracts/events.md` §2) y spec 056 (requisito 7). **Una sola tabla** para el
 * constructor (Rendimiento, `components/builder/improve-model.ts`) y para la
 * Bandeja (actividad, fila, hilo y caja de respuesta). Los textos son las claves
 * `waiting.reason.*` de `i18n/lanes/agent-improve.ts`. Puro: se prueba solo.
 *
 * La lista es `WAITING_REASONS` de `apps/api/src/nexus_api/db/models/conversation.py`,
 * más `taken_by_person`, que la API da como motivo del traspaso en Rendimiento.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

export const REASONS: ReadonlySet<string> = new Set([
  "no_balance",
  "agent_cap",
  "paused_agent",
  "paused_channel",
  "paused_client",
  "archived_client",
  "channel_problem",
  "agent_unpublished",
  "out_of_audience",
  "no_model",
  "provider_failure",
  "turn_limit",
  "escalated",
  "human_takeover",
  "reception_loop",
  // Spec 056 (requisito 1): el freno de citas pasó la conversación a una persona.
  "booking_unbacked",
  // Spec 057 (requisito 4.2): la agenda del cliente aún no está lista y el agente no
  // tiene la herramienta de derivar, así que el runtime pasó la cita a una persona.
  "agenda_not_ready",
  "taken_by_person",
]);

/** Lo que tiene forma de código (`snake_case`), no de frase del agente. */
const CODE = /^[a-z][a-z0-9_]*$/;

/** El motivo del traspaso, en palabras (`events.md` §2); un código nuevo, «Otro motivo». */
export function reasonKey(code: string | null): MessageKey | null {
  if (!code) return null;
  return (REASONS.has(code) ? `waiting.reason.${code}` : "waiting.reason.other") as MessageKey;
}

/**
 * El motivo como lo enseña la Bandeja (7.1, 7.2). Se le pasa primero el código
 * de la columna (`waiting_reason`/`waiting_code`) y, si no hay, el texto del aviso:
 *
 * - un código de la tabla da su texto («Sin saldo»);
 * - `escalated`, un código que la tabla no conoce, o nada, dan «El agente pidió
 *   ayuda»: la Bandeja nunca enseña un código;
 * - el texto libre del agente (la herramienta de escalar, hasta 500 caracteres)
 *   sale tal cual. *Decisión de la spec 056.*
 */
export function inboxReasonText(raw: string | null | undefined, t: T): string {
  const text = (raw ?? "").trim();
  if (text && text !== "escalated" && REASONS.has(text)) return t(`waiting.reason.${text}` as MessageKey);
  if (!text || CODE.test(text)) return t("inbox.event.escalated");
  return text;
}
