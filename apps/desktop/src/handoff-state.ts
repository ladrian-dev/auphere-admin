/**
 * El traspaso al navegador, y la vuelta — spec 010, Requisitos 9.4 y 9.5.
 *
 * Lo que había: «Elegir plan» y «Comprar saldo» salían al navegador **sin decir
 * nada**, y la ventana se quedaba exactamente igual mientras el pago ocurría
 * detrás. Al volver, nada se releía: el plan seguía diciendo lo de antes hasta
 * reiniciar la aplicación.
 *
 * Dos decisiones que se ven aquí:
 *
 * * **la espera tiene la misma forma que la de la entrada.** Son el mismo hecho
 *   —algo ocurre fuera de la ventana y hay que volver— y darle dos vocabularios
 *   distintos es cómo se acaban pintando dos esperas que no se parecen;
 * * **volver relee lo que pudo cambiar, no todo.** Recargar la aplicación
 *   entera al volver de pagar tira el hilo abierto y el borrador sin escribir,
 *   que es justo lo que R9.5 prohíbe al decir «sin reiniciar».
 */

export const HANDOFF_STATES = ["idle", "esperando", "vuelto", "cancelada", "caducada", "error"] as const;
export type HandoffState = (typeof HANDOFF_STATES)[number];

export type HandoffKind = "sign_in" | "payment";

export type HandoffView = { state: HandoffState; kind: HandoffKind | null; since: string; url?: string };

/**
 * Los orígenes del proveedor de pago y del proveedor de identidad.
 *
 * Se comparan **por host exacto**, nunca por `includes`: `checkout.stripe.com`
 * y `checkout.stripe.com.evil.example` se parecen lo bastante como para que la
 * comparación descuidada sea el fallo.
 */
const PAYMENT_HOSTS = new Set(["checkout.stripe.com", "billing.stripe.com"]);
const SIGN_IN_HOSTS = new Set(["accounts.google.com"]);

/** Qué clase de salida es, si es alguna. `null` = una salida sin vuelta. */
export function handoffKindFor(url: string): HandoffKind | null {
  let host: string;
  try {
    host = new URL(url).host.toLowerCase();
  } catch {
    return null;
  }
  if (PAYMENT_HOSTS.has(host)) return "payment";
  if (SIGN_IN_HOSTS.has(host)) return "sign_in";
  return null;
}

export function isWaitingHandoff(state: HandoffState): boolean {
  return state === "esperando";
}

/**
 * Qué hay que volver a leer al regresar. Nada más, y nunca un reinicio: el hilo
 * abierto y lo que estuviera escrito siguen donde estaban (R9.5).
 */
export function refetchOnReturn(kind: HandoffKind): string[] {
  return kind === "payment" ? ["membership", "usage"] : ["session"];
}
