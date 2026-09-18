/**
 * En qué punto está la entrada — spec 010, Requisitos 7.2 y 7.4.
 *
 * Puro, como todo lo que decide. El flujo por navegador vive en el proceso
 * principal (PKCE, oyente efímero, canje); esto sólo nombra en qué punto está,
 * para que la ventana no tenga que adivinarlo.
 *
 * Por qué existe: el anexo 04 documentó dos esperas mudas. Si la persona
 * cancela en Google, el retorno vuelve a `/login` sin destino y la aplicación
 * **espera los cinco minutos enteros** sin decir nada; sin pertenencia a
 * partner, lo mismo. Las dos veces la ventana se queda con «esperando» puesto
 * hasta que caduca, que es la peor forma de fallar: parece que va bien.
 */

export const SIGN_IN_STATES = ["idle", "esperando", "vuelto", "cancelada", "caducada", "error"] as const;
export type SignInState = (typeof SIGN_IN_STATES)[number];

/** Lo que el navegador acabó haciendo. `redeem_failed` es nuestro, no suyo. */
export type SignInReturn = { kind: "code" | "denied" | "timeout" | "redeem_failed" };

export type SignInView = {
  state: SignInState;
  /** Desde cuándo está así, para poder decir «llevas esperando N». */
  since: string;
  /** La dirección que se abrió, para poder reabrirla o copiarla (R7.2). */
  url?: string;
};

export function signInFrom(returned: SignInReturn, now: string): SignInView {
  // Cancelar es una decisión de la persona; que el canje falle es una avería.
  // Mezclarlas deja a alguien creyendo que cerró la pestaña sin querer.
  const state: SignInState =
    returned.kind === "code"
      ? "vuelto"
      : returned.kind === "denied"
        ? "cancelada"
        : returned.kind === "timeout"
          ? "caducada"
          : "error";
  return { state, since: now };
}

/** ¿Sigue esperando al navegador? Sólo uno de los seis lo está. */
export function isWaiting(state: SignInState): boolean {
  return state === "esperando";
}

/** Los tres desenlaces malos ofrecen volver a intentarlo. Ninguno calla. */
export function offersRetry(state: SignInState): boolean {
  return state === "cancelada" || state === "caducada" || state === "error";
}
