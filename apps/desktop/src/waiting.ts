/**
 * «Lo que te espera» — spec 010, Requisito 5.4.
 *
 * **Una sola definición** de la pregunta que cuatro superficies hacían por
 * separado: la lista lateral, el icono de la aplicación, el icono de la barra
 * del sistema y Pendientes. Hasta ahora cada una contaba a su manera —una
 * incluía lo informativo, otra no, otra cortaba en nueve—, así que la ventana
 * podía decir 4, 3 y 3 al mismo tiempo sobre el mismo hecho.
 *
 * La definición, y por qué:
 *
 * * **espera una decisión**: lo `informativo` no espera nada, es una nota. Un
 *   número que sube con cada nota es un número que nadie mira, y ese día el
 *   crítico tampoco se ve;
 * * **de esta persona**: lo que ella no puede decidir sigue estando en
 *   Pendientes —con a quién pedírselo, que para eso está—, pero no la persigue
 *   por el Dock. Un aviso que no se puede atender es ruido.
 *
 * El tope visual («9+») es **presentación**: la cifra sigue siendo la cifra.
 * Y lo que viaja a los iconos es sólo eso, una cifra: el icono se ve en una
 * pantalla compartida y el asunto se lee dentro de la aplicación.
 */

export type Level = "critico" | "aviso" | "informativo";

export type WaitingItem = {
  action_id: string;
  teammate_id: string;
  level: Level;
  /** Desde cuándo espera. Lo pinta Pendientes; la cifra no lo usa. */
  since: string;
  can_decide: boolean;
};

export type Waiting = {
  /** La cifra. La misma en las cuatro superficies. */
  count: number;
  /** Todo lo que está en la bandeja, cuente o no: Pendientes lo enseña entero. */
  items: readonly WaitingItem[];
};

/** Por encima de esto el número exacto ya no informa: informa que son muchas. */
const MANY = 9;

/**
 * Lo mínimo que hace falta para contar. Las cuatro superficies manejan formas
 * distintas del mismo hecho —la bandeja, la política de avisos, el icono— y
 * ninguna necesita convertirse a otra para preguntar lo mismo.
 */
export type Decidable = { level: Level; can_decide: boolean };

/** ¿Espera una decisión de esta persona? */
export function awaitsDecision(item: Decidable): boolean {
  return item.level !== "informativo" && item.can_decide;
}

/** La cifra, sobre cualquier lista que sepa decir nivel y si puede decidirse. */
export function countWaiting(items: readonly Decidable[]): number {
  return items.filter(awaitsDecision).length;
}

/** El derivado. Sin estado: es lo que hay, cada vez. */
export function waitingFrom(items: readonly WaitingItem[]): Waiting {
  return { count: countWaiting(items), items: [...items] };
}

/**
 * Cómo se escribe la cifra en un icono. `cap: false` donde hay sitio para el
 * número entero (la lista lateral), `true` donde no (los iconos del sistema).
 */
export function badgeText(waiting: Waiting, options: { cap?: boolean } = {}): string {
  const { cap = true } = options;
  if (waiting.count === 0) return "";
  return cap && waiting.count > MANY ? `${MANY}+` : String(waiting.count);
}
