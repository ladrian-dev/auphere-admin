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

import { badgeText, countWaiting, waitingFrom } from "./waiting.js";

export type Waiting = { level: "critico" | "aviso" | "informativo"; can_decide: boolean };

/**
 * La cifra y su tope salen de `waiting.ts`: aquí sólo se pintan. Es la misma
 * regla que usan la lista lateral, el icono de la aplicación y Pendientes.
 */
export function trayBadge(waiting: Waiting[]): string {
  return badgeText(waitingFrom(waiting.map(asItem)));
}

/** La bandeja sólo necesita nivel y si se puede decidir; el resto es relleno. */
const asItem = (w: Waiting) => ({
  action_id: "",
  teammate_id: "",
  since: "",
  level: w.level,
  can_decide: w.can_decide,
});

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
  const count = countWaiting(waiting);
  if (count === 0) return copy.none;
  return count === 1 ? copy.one : copy.many(count);
}
