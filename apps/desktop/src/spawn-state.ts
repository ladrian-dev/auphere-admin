/**
 * Qué estado de un subagente se puede afirmar — Requisitos 11.2, 11.3 y 11.4.
 *
 * **El listado del sustrato no es autoritativo.** La evaluación observó que su
 * `spawn list` informó `✅` de un subagente que su propia notificación registraba
 * como rechazado. Reflejar ese listado sería heredar la mentira, y §V no lo
 * admite: si algo no consta, se dice que no consta.
 *
 * De ahí que exista `desconocido`. Es un estado incómodo y a propósito: la
 * alternativa cómoda —asumir que corre porque aparece listado— es exactamente
 * la que produce una pantalla que miente.
 */

export type SpawnDisplayState =
  | "desconocido"
  | "rechazado"
  | "ejecutando"
  | "bloqueado"
  | "completado"
  | "fallado";

export type SpawnEvidence = {
  /** Lo que dice su listado. Es una **pista**, nunca la verdad. */
  listedAs: "ok" | "error" | null;
  /** Lo autoritativo: qué pasó con la aprobación. */
  approval: "approved" | "rejected" | null;
  finished: "completed" | "failed" | null;
  /** A quién espera, si espera. */
  waitingOn: string | null;
};

export function displayedSpawnState(evidence: SpawnEvidence): SpawnDisplayState {
  // El rechazo manda sobre cualquier cosa que diga el listado.
  if (evidence.approval === "rejected") return "rechazado";

  // Sin constancia de aprobación no se afirma que corra, liste lo que liste.
  if (evidence.approval !== "approved") return "desconocido";

  if (evidence.finished === "failed") return "fallado";
  if (evidence.finished === "completed") return "completado";

  // Esperar a otro es más informativo que "ejecutando", y evita pintar como
  // ocioso algo que sí está avanzando el trabajo de alguien.
  if (evidence.waitingOn) return "bloqueado";

  return "ejecutando";
}
