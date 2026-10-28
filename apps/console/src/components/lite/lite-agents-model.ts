import type { MessageKey } from "@/i18n/messages";
import type { LiteAgent } from "@/lib/backend/lite-agents";
import type { CorrectionPii } from "@/lib/backend/inbox-corrections";

/**
 * Spec 047 (T168, T176) — las cuentas puras de la consola lite: quién pausó un
 * agente y por qué (la frase bajo su estado) y dónde están los datos de un
 * cliente final en una corrección. Sin React: se prueban solas.
 */

export type PauseLine = { key: MessageKey; name: string | null };

/**
 * La frase bajo el estado de un agente en pausa: quién (por su nombre, 27.6) y
 * desde dónde, o cuándo se quita sola una pausa del sistema. `null` si atiende.
 */
export function pauseLine(
  agent: Pick<LiteAgent, "visible_state" | "pause_reason" | "paused_by_kind" | "paused_origin" | "paused_by_name">,
): PauseLine | null {
  if (agent.visible_state.code !== "paused") return null;
  const reason = agent.pause_reason ?? agent.visible_state.reason ?? "manual";
  const system = (key: MessageKey): PauseLine => ({ key, name: null });
  if (reason === "no_balance") return system("lite.agents.system.no_balance");
  if (reason === "agent_cap") return system("lite.agents.system.agent_cap");
  if (reason === "client_paused" || reason === "client_archived") return system("lite.agents.system.client_paused");
  if (agent.paused_by_kind === "client_user") {
    const name = agent.paused_by_name?.trim() || null;
    const where = agent.paused_origin === "app" ? "app" : "web";
    return { key: `lite.agents.pausedBy.${where}${name ? "Named" : ""}` as MessageKey, name };
  }
  return system("lite.agents.pausedBy.partner");
}

export type PiiSpan = { field: "lesson" | "paraphrase"; kind: string; text: string };

/**
 * Lo que hay que quitar, con el trozo de texto de la persona (la API manda las
 * posiciones, nunca el dato). Una posición que ya no cae dentro del texto —la
 * persona lo cambió— se ignora: el siguiente envío la vuelve a buscar.
 */
export function piiSpans(pii: readonly CorrectionPii[], texts: { lesson: string; paraphrase: string | null }): PiiSpan[] {
  const out: PiiSpan[] = [];
  for (const p of pii) {
    const source = p.field === "lesson" ? texts.lesson : (texts.paraphrase ?? "");
    if (p.start < 0 || p.end > source.length || p.end <= p.start) continue;
    out.push({ field: p.field, kind: p.kind, text: source.slice(p.start, p.end) });
  }
  return out;
}

const PII_KINDS = new Set(["email", "document", "phone", "name"]);

/** «Un teléfono», «un correo»… el nombre del tipo de dato. */
export function piiKindKey(kind: string): MessageKey {
  return (PII_KINDS.has(kind) ? `lite.correct.pii.${kind}` : "lite.correct.pii.other") as MessageKey;
}

/** Una clave por intento: si la red repite la petición, la API no aplica el cambio dos veces. */
export function idempotencyKey(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
