/**
 * Los permisos del sistema operativo — spec 010, Requisitos 7.8 y 7.10.
 *
 * **`desconocido` existe a propósito.** macOS no deja consultar el estado de
 * los avisos: `systemPreferences.getMediaAccessStatus` cubre cámara y
 * micrófono, y no hay equivalente para éstos. Antes de intentar mostrar uno,
 * no consta — y asumir «concedido» pondría la lista de puesta en marcha a decir
 * que algo está hecho sin saberlo, que es exactamente lo que §V prohíbe.
 *
 * La regla de cuándo se pide: **al usarlo por primera vez**. Pedirlos al
 * arrancar, todos de golpe y sin contexto, es la razón por la que la gente los
 * deniega — nadie concede acceso a algo que todavía no sabe para qué es.
 */

export const PERMISSION_STATES = ["desconocido", "concedido", "denegado"] as const;
export type PermissionState = (typeof PERMISSION_STATES)[number];

export type Permission = "notifications";

/** ¿Se llegó a pedir alguna vez? `desconocido` es «todavía no». */
export function askedFor(state: PermissionState): boolean {
  return state !== "desconocido";
}

/**
 * Lo que se sabe después de intentar usarlo.
 *
 * Un intento que **no** sale no degrada un permiso ya concedido: puede ser
 * «No molestar», la pantalla compartida o un foco activo. Tratar eso como una
 * denegación pondría la lista a mentir en la otra dirección.
 */
export function nextAfterAttempt(state: PermissionState, attempt: { shown: boolean }): PermissionState {
  if (attempt.shown) return "concedido";
  return state === "concedido" ? "concedido" : "denegado";
}

/** La clave del texto que explica **para qué** se pide, antes de pedirlo. */
export function explains(permission: Permission): string {
  return `permission.${permission}.why`;
}

/**
 * Qué se pierde, qué sigue funcionando, y dónde se concede.
 *
 * Las tres cosas juntas: nombrar sólo la pérdida hace que denegar parezca haber
 * roto la aplicación, y nombrar sólo el remedio no dice por qué merece la pena.
 * El destino es el panel concreto de Ajustes del sistema, no «busca en
 * Ajustes»: llevar a la acción, no explicarla.
 */
export function losesWhenDenied(permission: Permission): {
  loses: string;
  keeps: string;
  settings: string;
} {
  return {
    loses: `permission.${permission}.loses`,
    keeps: `permission.${permission}.keeps`,
    settings: "x-apple.systempreferences:com.apple.preference.notifications",
  };
}
