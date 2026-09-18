/**
 * Los tres niveles de aviso, como política — spec 003, Requisito 7.
 *
 * Puro: recibe lo que espera y qué prefiere la persona, y dice **qué se hace**.
 * El proceso principal solo ejecuta lo que esto decide, y por eso las reglas se
 * pueden leer aquí en veinte líneas en vez de perseguirlas por `main.ts`.
 *
 * Tres reglas que son producto, no implementación:
 *
 * * `critico` interrumpe con un aviso del sistema; `aviso` marca la bandeja;
 *   `informativo` no hace nada. Nunca al revés.
 * * Al abrir con cosas esperando se avisa **una vez, en resumen** — una
 *   notificación por tarjeta al arrancar es ruido, y el ruido enseña a ignorar.
 * * La persona puede **bajar** el ruido (silenciar `aviso`), nunca subirlo: un
 *   nivel que se pudiera inflar dejaría de significar nada.
 */

export const LEVELS = ["critico", "aviso", "informativo"] as const;
import { countWaiting } from "./waiting.js";

export type Level = (typeof LEVELS)[number];

export type Pending = { action_id: string; level: Level; teammate: string; title: string; can_decide: boolean };

export type Prefs = { silenceAviso: boolean };

export type Effect =
  | { kind: "none" }
  | { kind: "notify"; title: string; body: string; actionId: string | null }
  | { kind: "badge"; count: number };

export const DEFAULT_PREFS: Prefs = { silenceAviso: false };

/**
 * El badge cuenta lo que espera de verdad. **La regla no vive aquí**: vive en
 * `waiting.ts`, y la comparten las cuatro superficies. Antes cada una tenía la
 * suya y la ventana podía decir tres cifras distintas del mismo hecho.
 */
export function badgeCount(pending: Pending[]): number {
  return countWaiting(pending);
}

/**
 * El contexto que decide si el sistema operativo entra en juego — spec 010,
 * R5.5, R5.6 y R12.2.
 */
export type NotifyContext = {
  /** Con la ventana delante, lo de dentro ya se ve: no se grita por fuera. */
  windowFocused: boolean;
  /** El idioma de la cuenta. El resumen estaba sólo en español. */
  lang: Lang;
};

export type Lang = "es" | "en";

/**
 * Lo que dice un aviso del sistema. **El motivo, nunca el contenido** (R5.6).
 *
 * El cuerpo era el título de la propuesta, y ahí acababa el comando literal o
 * el nombre del cliente final, en el centro de notificaciones del sistema —una
 * superficie que se ve en una pantalla compartida y sin sesión delante.
 */
const COPY = {
  es: {
    waitingOne: "Espera tu decisión",
    waitingMany: (n: number) => `${n} cosas esperan tu decisión`,
  },
  en: {
    waitingOne: "Waiting for your decision",
    waitingMany: (n: number) => `${n} things are waiting for your decision`,
  },
} as const;

const copy = (lang: Lang) => COPY[lang] ?? COPY.es;

/** Un aviso por teammate, no uno por tarjeta: el ruido enseña a ignorar. */
function byTeammate(items: Pending[]): Array<{ teammate: string; items: Pending[] }> {
  const groups: Array<{ teammate: string; items: Pending[] }> = [];
  for (const item of items) {
    const group = groups.find((g) => g.teammate === item.teammate);
    if (group) group.items.push(item);
    else groups.push({ teammate: item.teammate, items: [item] });
  }
  return groups;
}

function summarise(group: { teammate: string; items: Pending[] }, lang: Lang, single: boolean): Effect {
  const c = copy(lang);
  return {
    kind: "notify",
    title: group.teammate,
    body: group.items.length === 1 ? c.waitingOne : c.waitingMany(group.items.length),
    // Con una sola en toda la bandeja, el aviso lleva a su tarjeta; si hay más
    // de una, llevar a una concreta sería elegir por la persona.
    actionId: single && group.items[0] ? group.items[0].action_id : null,
  };
}

/** Un aviso que llega con la aplicación abierta. */
export function onArrival(item: Pending, prefs: Prefs, pending: Pending[], context: NotifyContext): Effect[] {
  const effects: Effect[] = [{ kind: "badge", count: badgeCount(pending) }];
  // R5.5 y regla 4 del contrato: con la ventana delante no se sale al sistema.
  // El número sí sube — no interrumpe a nadie — y la tarjeta aparece sola.
  if (context.windowFocused) return effects;
  if (item.level === "critico") {
    effects.push(summarise({ teammate: item.teammate, items: [item] }, context.lang, true));
  }
  // `aviso` marca la bandeja y nada más; silenciarlo no la deja sin marcar,
  // porque el badge no interrumpe: solo el aviso del sistema lo hace.
  return effects;
}

/** Lo que se hace al abrir la aplicación con cosas ya esperando. */
export function onOpen(pending: Pending[], prefs: Prefs, context: NotifyContext): Effect[] {
  const effects: Effect[] = [{ kind: "badge", count: badgeCount(pending) }];
  if (context.windowFocused) return effects;
  const ruidosas = pending.filter((p) => p.level === "critico" || (p.level === "aviso" && !prefs.silenceAviso));
  if (ruidosas.length === 0) return effects;
  const grupos = byTeammate(ruidosas);
  for (const grupo of grupos) effects.push(summarise(grupo, context.lang, ruidosas.length === 1));
  return effects;
}

/** La preferencia solo puede bajar el ruido. */
export function normalisePrefs(input: Partial<Prefs> | undefined): Prefs {
  return { silenceAviso: input?.silenceAviso === true };
}
