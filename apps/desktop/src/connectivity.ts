/**
 * La conectividad — spec 010, Requisitos 3.1 y 3.2.
 *
 * Tres estados, y el tercero es el que arregla el fallo:
 *
 * * `online` — la plataforma contesta. Lo que diga, manda.
 * * `offline` — no se pudo llegar. **No quiere decir que no haya sesión.**
 * * `unconfirmed` — se intentó y no se pudo interpretar la respuesta.
 *
 * Hasta ahora sólo había dos, implícitos, y cualquier excepción al preguntar
 * quién está dentro se convertía en «nadie ha iniciado sesión»: la aplicación
 * mandaba a la persona a iniciar sesión **sin red**, encima de la página de
 * error del navegador. De ahí la regla de `keepsLastVerdict`: mientras no se
 * pueda confirmar, se conserva lo último que se supo y se marca como no
 * confirmado, en vez de afirmar algo nuevo.
 */

export type ConnectivityState = "online" | "offline" | "unconfirmed";

export type Connectivity = {
  state: ConnectivityState;
  /** Desde cuándo (ISO-8601). Para poder decir «sin conexión desde las 20:14». */
  since: string;
};

/** Por qué falló el intento. `network` es no haber llegado siquiera. */
export type Failure = { kind: "network" | "unknown" };

const move = (previous: Connectivity, state: ConnectivityState, now: string): Connectivity =>
  previous.state === state ? previous : { state, since: now };

/** La plataforma contestó — aunque contestara que no hay sesión. */
export function noteSuccess(previous: Connectivity, now: string): Connectivity {
  return move(previous, "online", now);
}

/** No se pudo llegar, o no se pudo interpretar lo que llegó. */
export function noteFailure(previous: Connectivity, failure: Failure, now: string): Connectivity {
  return move(previous, failure.kind === "network" ? "offline" : "unconfirmed", now);
}

/**
 * ¿Hay que conservar el último veredicto de sesión?
 *
 * Sí siempre que no se haya podido confirmar: es la diferencia entre «te has
 * desconectado» y «no he podido preguntar».
 */
export function keepsLastVerdict(connectivity: Connectivity): boolean {
  return connectivity.state !== "online";
}

/** El estado inicial a partir de lo que vio el último intento, si hubo alguno. */
export function connectivityFrom(failure: Failure | null, now: string): Connectivity {
  if (failure === null) return { state: "unconfirmed", since: now };
  return { state: failure.kind === "network" ? "offline" : "unconfirmed", since: now };
}
