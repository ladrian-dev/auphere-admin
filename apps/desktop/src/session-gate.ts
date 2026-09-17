/**
 * La puerta de sesión — Requisitos 2.2, 2.4 y 11.1; Historia 5 (spec 002).
 *
 * **Quién está dentro lo lee el proceso principal, no la página.** `whoami` es
 * una ruta del BFF de la consola llamada con la cookie de la partición humana
 * desde el proceso principal; la página cargada no participa, y el ambiente del
 * agente no tiene esa partición ni ese proceso. Es lo que hace ciertas dos
 * cosas sin abrir canal alguno: «cerrar sesión detiene el puente» y «la misma
 * persona vuelve sin código».
 *
 * Sin sesión o sin pertenencia la respuesta es la misma: parar, y **no ofrecer
 * emparejar** (2.4). Otra persona con sesión en una máquina emparejada por
 * alguien ve la oferta de emparejar la suya, y **nunca** a quién pertenece la
 * otra credencial.
 */
import type { Connectivity } from "./connectivity.js";
import { connectivityFrom, noteFailure, noteSuccess } from "./connectivity.js";
import type { CredentialStore, StoredCredential } from "./credential-store.js";

export type Whoami =
  | { kind: "anonymous" }
  | { kind: "no_membership" }
  | { kind: "member"; userId: string; partnerSlug: string; locale?: "es" | "en"; permissions?: string[] };

export interface WhoamiClient {
  whoami(): Promise<Whoami>;
}

export type GateDecision =
  | { kind: "start"; userId: string; credential: StoredCredential; locale?: "es" | "en" }
  | { kind: "stop"; reason: "anonymous" | "no_membership" }
  | { kind: "pair_needed"; userId: string; pairedByOther: boolean; locale?: "es" | "en" }
  /**
   * Spec 010 R3.2 — **no se pudo preguntar**.
   *
   * No es «no hay nadie»: es que no hubo respuesta. Sólo aparece cuando no hay
   * ningún veredicto anterior que conservar —arrancar sin red—, y lo que hay
   * que enseñar entonces es el armazón con «sin conexión», nunca el inicio de
   * sesión.
   */
  | { kind: "unconfirmed" };

export interface SessionCookieWatcher {
  onSessionCookieChanged(callback: () => void): void;
}

export class SessionGate {
  private readonly whoami: WhoamiClient;
  private readonly store: CredentialStore;
  private listeners: Array<(decision: GateDecision) => void> = [];
  /** El último veredicto **confirmado**: lo que se conserva si no se puede preguntar. */
  private last: GateDecision | null = null;
  private link: Connectivity = connectivityFrom(null, new Date().toISOString());

  constructor(options: { whoami: WhoamiClient; store: CredentialStore }) {
    this.whoami = options.whoami;
    this.store = options.store;
  }

  /** Cómo está la conexión según el último intento. Lo lee el armazón. */
  connectivity(): Connectivity {
    return this.link;
  }

  async evaluate(now: string = new Date().toISOString()): Promise<GateDecision> {
    let who: Whoami;
    try {
      who = await this.whoami.whoami();
    } catch {
      /*
       * Spec 010 R3.2. Antes esto se convertía en «nadie ha iniciado sesión»,
       * y la aplicación mandaba a la persona al inicio de sesión **sin red**.
       * No poder preguntar no es una respuesta: se conserva el último veredicto
       * confirmado y se marca la conexión como caída.
       */
      this.link = noteFailure(this.link, { kind: "network" }, now);
      return this.last ?? { kind: "unconfirmed" };
    }
    this.link = noteSuccess(this.link, now);
    if (who.kind === "anonymous") return this.remember({ kind: "stop", reason: "anonymous" });
    if (who.kind === "no_membership") return this.remember({ kind: "stop", reason: "no_membership" });
    const credential = this.store.get(who.userId);
    const locale = who.locale;
    if (credential) return this.remember({ kind: "start", userId: who.userId, credential, ...(locale ? { locale } : {}) });
    const others = this.store.users().filter((u) => u !== who.userId);
    return this.remember({
      kind: "pair_needed",
      userId: who.userId,
      pairedByOther: others.length > 0,
      ...(locale ? { locale } : {}),
    });
  }

  /** Lo confirmado se recuerda: es lo que se conserva cuando no hay respuesta. */
  private remember(decision: GateDecision): GateDecision {
    this.last = decision;
    return decision;
  }

  onDecision(listener: (decision: GateDecision) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  /** Vuelve a preguntar y avisa a quien escucha. Lo usa la cookie y, desde la
   *  spec 003, la pantalla cuando el BFF contesta «sin sesión». */
  async refresh(): Promise<GateDecision> {
    const decision = await this.evaluate();
    for (const listener of this.listeners) listener(decision);
    return decision;
  }

  /** Cada cambio de la cookie de sesión vuelve a preguntar. La caducidad es un cambio más. */
  watch(watcher: SessionCookieWatcher): void {
    watcher.onSessionCookieChanged(() => void this.refresh());
  }
}
