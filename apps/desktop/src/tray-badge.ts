/**
 * El conteo de la bandeja — spec 003, Requisito 12.4.
 *
 * Es lo único de la aplicación que se ve con la ventana cerrada, y por eso
 * cuenta **lo que espera una decisión** y no «lo nuevo». Un número que sube con
 * cada nota informativa se vuelve un número que nadie mira, y ese día el
 * crítico tampoco se ve — que es exactamente lo que la bandeja existía para
 * evitar (la misma regla que `notifications-policy.ts` aplica al aviso del
 * sistema: el nivel decide, no la novedad).
 *
 * Y no dice **de qué** va: el icono se ve en una pantalla compartida, sin
 * sesión delante. El asunto se lee dentro de la aplicación.
 */

export type Waiting = { level: "critico" | "aviso" | "informativo" };

/** Por encima de esto el número exacto ya no informa: informa que son muchas. */
const MANY = 9;

const decides = (item: Waiting): boolean => item.level !== "informativo";

export function trayBadge(waiting: Waiting[]): string {
  const count = waiting.filter(decides).length;
  if (count === 0) return "";
  return count > MANY ? `${MANY}+` : String(count);
}

const COPY = {
  es: {
    none: "Nada te espera",
    one: "1 cosa espera tu decisión",
    many: (n: number) => `${n} cosas esperan tu decisión`,
  },
  en: {
    none: "Nothing is waiting for you",
    one: "1 thing is waiting for your decision",
    many: (n: number) => `${n} things are waiting for your decision`,
  },
} as const;

export function trayTooltip(waiting: Waiting[], lang: "es" | "en"): string {
  const copy = COPY[lang] ?? COPY.es;
  const count = waiting.filter(decides).length;
  if (count === 0) return copy.none;
  return count === 1 ? copy.one : copy.many(count);
}
