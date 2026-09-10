/**
 * Los estados de la pantalla, derivados y nunca almacenados — spec 003, R3.4.
 *
 * Puro. Recibe lo que el hilo sabe (estado de carga, del run, reconexión,
 * parcial), lo que la tarea dice (`task.state`), lo que el presupuesto dice y
 * lo que la máquina dice, y devuelve **un** estado nombrado. Ninguno se pinta
 * en rojo; la ausencia de máquina es una espera diseñada, no un fallo.
 */

export const THREAD_STATES = [
  "normal",
  "cargando",
  "vacio",
  "error",
  "reconectando",
  "parcial",
  "esperandote",
  "en_pausa_por_tope",
  "maquina_ausente",
] as const;
export type ThreadState = (typeof THREAD_STATES)[number];

export const TASK_STATES = ["en_marcha", "esperandote", "pausada_por_tope", "terminada", "cancelada", "caducada"] as const;
export type TaskState = (typeof TASK_STATES)[number];

export type ThreadFacts = {
  status: "loading" | "error" | "ready";
  runStatus: "idle" | "running" | "completed" | "cancelled" | "error" | "interrupted" | "paused" | "waiting";
  reconnecting: boolean;
  partial: boolean;
  itemCount: number;
  taskState: TaskState | null;
  budgetPaused: boolean;
  /** El teammate necesita la máquina y no está presente. */
  machineNeeded: boolean;
  machinePresent: boolean;
};

export function deriveThreadState(f: ThreadFacts): ThreadState {
  if (f.status === "loading") return "cargando";
  if (f.status === "error") return "error";
  if (f.reconnecting) return "reconectando";
  if (f.budgetPaused || f.runStatus === "paused" || f.taskState === "pausada_por_tope") return "en_pausa_por_tope";
  if (f.taskState === "esperandote" || f.runStatus === "waiting") return "esperandote";
  if (f.machineNeeded && !f.machinePresent) return "maquina_ausente";
  if (f.partial) return "parcial";
  if (f.itemCount === 0) return "vacio";
  return "normal";
}

/** Ninguno de los nueve se pinta como error, salvo `error`, que es la pantalla y no el trabajo. */
export function isFailure(state: ThreadState): boolean {
  return state === "error";
}

export type RosterEntry = {
  id: string;
  my_state: "en_marcha" | "esperandote" | "en_pausa_por_tope" | "en_espera";
  my_unread: boolean;
};

/** `task.state` llega por el stream: el roster lo refleja sin recargar. */
export function applyTaskState<T extends RosterEntry>(
  roster: T[],
  teammateId: string,
  state: TaskState,
): T[] {
  const my: RosterEntry["my_state"] =
    state === "en_marcha" ? "en_marcha" : state === "esperandote" ? "esperandote" : state === "pausada_por_tope" ? "en_pausa_por_tope" : "en_espera";
  return roster.map((r) => (r.id === teammateId ? { ...r, my_state: my, my_unread: state === "terminada" ? true : r.my_unread } : r));
}

export type InboxItem = { action_id: string; decided?: "confirm" | "edit" | "cancel" | null };

/** `inbox.changed`: la tarjeta desaparece de la bandeja sin recargar. */
export function applyInboxChanged<T extends InboxItem>(inbox: T[], actionId: string): T[] {
  return inbox.filter((i) => i.action_id !== actionId);
}
