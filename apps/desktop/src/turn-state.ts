/**
 * Los ocho estados de un turno — spec 010, Requisito 4.3.
 *
 * Derivados y nunca almacenados, por la misma razón que `deriveThreadState`:
 * un estado guardado es una segunda verdad, y la primera reconexión que se
 * salte un evento la deja mintiendo para siempre.
 *
 * Esto es más fino que el estado de la **pantalla**: `deriveThreadState` dice
 * en qué está el hilo (cargando, vacío, reconectando, esperándote…), y esto
 * dice en qué está el **turno** que corre dentro de él. Hasta la spec 010 el
 * hilo solo distinguía dos cosas —el botón de enviar cambiaba a un cuadrado, y
 * nada más—, así que razonar, llamar a una herramienta y esperar la primera
 * palabra del servidor se veían idénticos.
 */

export const TURN_STATES = [
  "enviando",
  "esperando",
  "razonando",
  "herramienta",
  "esperando_decision",
  "terminado",
  "detenido",
  "fallido",
] as const;
export type TurnState = (typeof TURN_STATES)[number];

/** El mismo conjunto que `RunStatus` del paquete compartido, redeclarado para
 *  que este módulo siga siendo puro y comprobable sin React ni transporte. */
export type TurnRunStatus =
  | "idle"
  | "running"
  | "completed"
  | "cancelled"
  | "error"
  | "interrupted"
  | "paused"
  | "waiting";

export type TurnFacts = {
  /** El envío salió de aquí y el servidor todavía no abrió el turno. */
  sending: boolean;
  runStatus: TurnRunStatus;
  /** Hay un bloque de pensamiento sin cerrar. */
  thinking: boolean;
  /** El nombre humano de la herramienta en marcha, si la hay. */
  tool: string | null;
  /** Hay una tarjeta esperando una decisión de esta persona. */
  awaitingDecision: boolean;
};

export function deriveTurnState(f: TurnFacts): TurnState | null {
  // Lo que la persona tiene que hacer gana a lo que la máquina esté haciendo:
  // si hay una tarjeta esperando, el turno está parado en ella aunque el
  // stream siga abierto.
  if (f.awaitingDecision) return "esperando_decision";
  if (f.sending) return "enviando";
  if (f.runStatus === "error" || f.runStatus === "interrupted") return "fallido";
  if (f.runStatus === "cancelled") return "detenido";
  // El tope **no es un fallo** ni una detención: el turno cerró limpio y lo
  // hecho sigue arriba. Que además haya tope lo dice el compositor, con sus
  // números y su salida; repetirlo aquí serían dos avisos de lo mismo.
  if (f.runStatus === "completed" || f.runStatus === "paused") return "terminado";
  if (f.runStatus === "waiting") return "esperando_decision";
  if (f.runStatus === "running") {
    if (f.tool !== null) return "herramienta";
    if (f.thinking) return "razonando";
    return "esperando";
  }
  return null;
}

/**
 * Requisito 4.4 — se ofrece detener **mientras trabaja**, en los tres estados
 * y no en uno.
 *
 * Y no se ofrece donde no hay nada que detener: `stop()` sin turno vivo vuelve
 * en silencio, que es exactamente el fallo mudo que la historia 3 persigue.
 */
export function offersStop(state: TurnState | null): boolean {
  return state === "esperando" || state === "razonando" || state === "herramienta";
}

/** Los estados que se anuncian en pantalla. `terminado` no deja cartel puesto
 *  —la respuesta es el anuncio— y `esperando_decision` lo dice su tarjeta. */
export function announces(state: TurnState | null): boolean {
  return state !== null && state !== "terminado" && state !== "esperando_decision";
}

/** Lo mínimo que hace falta del hilo, con la forma que ya tiene. */
type ThreadShape = {
  runStatus: TurnRunStatus;
  items: ReadonlyArray<Record<string, unknown>>;
};

/** Lee los hechos del hilo. Nada se guarda: se mira lo que hay. */
export function turnFactsOf(state: ThreadShape, sending: boolean): TurnFacts {
  let thinking = false;
  let tool: string | null = null;
  let awaitingDecision = false;
  for (const item of state.items) {
    if (item.kind === "thinking" && item.endedAt === null) thinking = true;
    if (item.kind === "tool" && item.status === "running") {
      const label = item.label;
      // El catálogo da la etiqueta humana; sin ella, el nombre técnico es
      // mejor que «trabajando», que no distingue nada.
      tool = typeof label === "string" && label !== "" ? label : typeof item.name === "string" ? item.name : null;
    }
    if (item.kind === "action" && item.state === "pending") awaitingDecision = true;
  }
  return { sending, runStatus: state.runStatus, thinking, tool, awaitingDecision };
}
