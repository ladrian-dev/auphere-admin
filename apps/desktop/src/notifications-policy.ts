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
export type Level = (typeof LEVELS)[number];

export type Pending = { action_id: string; level: Level; teammate: string; title: string };

export type Prefs = { silenceAviso: boolean };

export type Effect =
  | { kind: "none" }
  | { kind: "notify"; title: string; body: string; actionId: string | null }
  | { kind: "badge"; count: number };

export const DEFAULT_PREFS: Prefs = { silenceAviso: false };

/** El badge cuenta lo que espera de verdad: `informativo` no marca nada. */
export function badgeCount(pending: Pending[]): number {
  return pending.filter((p) => p.level !== "informativo").length;
}

/** Un aviso que llega con la aplicación abierta. */
export function onArrival(item: Pending, prefs: Prefs, pending: Pending[]): Effect[] {
  const effects: Effect[] = [{ kind: "badge", count: badgeCount(pending) }];
  if (item.level === "critico") {
    effects.push({
      kind: "notify",
      title: item.teammate,
      body: item.title,
      actionId: item.action_id,
    });
  }
  // `aviso` marca la bandeja y nada más; silenciarlo no la deja sin marcar,
  // porque el badge no interrumpe: solo el aviso del sistema lo hace.
  return effects;
}

/** Lo que se hace al abrir la aplicación con cosas ya esperando. */
export function onOpen(pending: Pending[], prefs: Prefs): Effect[] {
  const effects: Effect[] = [{ kind: "badge", count: badgeCount(pending) }];
  const criticos = pending.filter((p) => p.level === "critico");
  const avisos = pending.filter((p) => p.level === "aviso");
  const loud = criticos.length > 0 || (avisos.length > 0 && !prefs.silenceAviso);
  if (!loud) return effects;
  const total = criticos.length + avisos.length;
  effects.push({
    kind: "notify",
    title: total === 1 ? (criticos[0] ?? avisos[0])!.teammate : "Tu equipo te espera",
    body:
      total === 1
        ? (criticos[0] ?? avisos[0])!.title
        : `${total} decisiones esperando`,
    // Con una sola, el aviso lleva a su tarjeta; con varias, a la bandeja.
    actionId: total === 1 ? (criticos[0] ?? avisos[0])!.action_id : null,
  });
  return effects;
}

/** La preferencia solo puede bajar el ruido. */
export function normalisePrefs(input: Partial<Prefs> | undefined): Prefs {
  return { silenceAviso: input?.silenceAviso === true };
}
