import type { MessageKey } from "@/i18n/messages";
import type { CorrectionPii } from "@/lib/backend/inbox-corrections";

/**
 * Spec 047 (T176) — las cuentas puras de «Corregir esta respuesta»: dónde están
 * los datos de un cliente final en una corrección. Sin React: se prueban solas.
 * La frase de quién pausó un agente se fue con Agentes del cliente (spec 056).
 */

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
