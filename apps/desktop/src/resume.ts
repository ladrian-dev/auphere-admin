/**
 * Reanudar lo que quedó en pausa — spec 010, Requisito 9.11.
 *
 * El caso: el pool de la semana se agota a mitad de un trabajo. El turno cierra
 * **limpio** —con lo hecho arriba, sus tokens y su historia— y la tarea queda
 * `pausada_por_tope`. Cuando la causa se resuelve (llega el lunes, o alguien
 * compra saldo), lo pausado tiene que poder seguir **sin empezar de nuevo**:
 * volver a pedir lo mismo gastaría otra vez lo que ya se gastó, y encima
 * llegaría a un resultado distinto.
 *
 * Puro: aquí sólo se decide **qué se puede reanudar y cuándo**. Reanudar es
 * la tarea durable que ya existe, y la lleva la plataforma.
 */

import type { TaskState } from "./app-state.js";

export type PauseCause = "pool_agotado" | "cobro_fallido";

export type ResumeFacts = {
  taskState: TaskState | null;
  /** Si la causa de la pausa sigue en pie. */
  stillCapped: boolean;
};

/**
 * ¿Se puede reanudar esto ahora?
 *
 * Sólo lo pausado por tope, y sólo con la causa resuelta. Ofrecer «reanudar»
 * con el pool todavía agotado es un botón que devuelve el mismo 409, que es
 * exactamente el fallo mudo que la historia 3 persigue.
 */
export function canResume(f: ResumeFacts): boolean {
  return f.taskState === "pausada_por_tope" && !f.stillCapped;
}

/**
 * Lo que se ofrece mientras la causa sigue en pie: no reanudar, sino **lo que
 * la resuelve**. Un estado sin salida es lo que R9.1 prohíbe.
 */
export function blockedBy(f: ResumeFacts): PauseCause | null {
  return f.taskState === "pausada_por_tope" && f.stillCapped ? "pool_agotado" : null;
}

/**
 * Cuántas tareas quedaron en pausa. Se cuenta, no se lista: reanudar de una en
 * una es lo correcto —cada una gasta— pero saber cuántas hay es lo que deja
 * decidir si merece la pena comprar saldo.
 */
export function pausedCount(tasks: ReadonlyArray<{ state: TaskState }>): number {
  return tasks.filter((t) => t.state === "pausada_por_tope").length;
}
