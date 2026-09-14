import type { SignupRowOut } from "@/lib/backend";

/**
 * Vocabulario del alta autónoma para el panel — spec 006, Requisito 8.
 *
 * Vive fuera de la página porque es lo único con criterio dentro: qué se
 * considera «a medias», cómo se nombra una vía de entrada y qué se puede
 * reenviar. Una tabla se mira; esto se comprueba.
 */

/** `password` en la API; aquí se dice en el idioma del panel. */
export function entryRouteLabel(provider: SignupRowOut["provider"]): string {
  return provider === "google" ? "Google" : "Contraseña";
}

export function signupStatusLabel(status: SignupRowOut["status"]): string {
  switch (status) {
    case "pending":
      return "A medias";
    case "consumed":
      return "Completada";
    case "expired":
      return "Caducada";
    case "revoked":
      return "Reemplazada";
  }
}

export function signupTone(
  status: SignupRowOut["status"],
): "positive" | "warning" | "muted" {
  if (status === "consumed") return "positive";
  // Pendiente es **aviso**, no «todo bien»: hay alguien esperando con un reloj
  // corriendo. Caducada y reemplazada ya no piden nada de nadie.
  if (status === "pending") return "warning";
  return "muted";
}

/**
 * Un registro a medias: correo verificado, empresa sin nombrar.
 *
 * **La señal es que no hay partner, no que el estado sea `pending`.** Son lo
 * mismo hoy, y separarlos evita que mañana un estado nuevo cuele una fila sin
 * empresa como si fuera una empresa.
 */
export function isHalfFinished(row: SignupRowOut): boolean {
  return row.partner === null && row.status === "pending";
}

/** Sólo lo vivo se reenvía: lo consumido ya tiene cuenta, lo caducado caducó. */
export function canResend(row: SignupRowOut): boolean {
  return row.status === "pending" && new Date(row.expires_at).getTime() > Date.now();
}
