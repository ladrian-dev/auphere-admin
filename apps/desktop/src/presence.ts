/**
 * Device presence — Requisito 4.1 y 4.2.
 *
 * El estado NO se almacena: se deriva del último latido. Guardar un booleano
 * invitaría a que la pantalla siguiera diciendo "conectado" cuando el proceso que
 * debía actualizarlo ha muerto, y §V no admite una pantalla que miente.
 *
 * Las cadencias siguen la convención de Kubernetes y Consul —latido cada 10 s,
 * caducidad a los 30 s— y caben holgadas dentro del minuto que exige CE-004.
 */

export const HEARTBEAT_INTERVAL_MS = 10_000;
export const PRESENCE_EXPIRY_MS = 30_000;

export type Presence = "presente" | "ausente";

/** Deriva la presencia. `lastHeartbeatAt` en milisegundos epoch; `null` = nunca visto. */
export function derivePresence(lastHeartbeatAt: number | null, now: number): Presence {
  if (lastHeartbeatAt === null) return "ausente";
  return now - lastHeartbeatAt < PRESENCE_EXPIRY_MS ? "presente" : "ausente";
}

/** Segundos desde el último latido, para el texto de estado que ve el partner. */
export function secondsSinceHeartbeat(lastHeartbeatAt: number | null, now: number): number | null {
  return lastHeartbeatAt === null ? null : Math.max(0, Math.floor((now - lastHeartbeatAt) / 1000));
}
