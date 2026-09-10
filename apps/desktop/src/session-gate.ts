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
import type { CredentialStore, StoredCredential } from "./credential-store.js";

export type Whoami =
  | { kind: "anonymous" }
  | { kind: "no_membership" }
  | { kind: "member"; userId: string; partnerSlug: string };

export interface WhoamiClient {
  whoami(): Promise<Whoami>;
}

export type GateDecision =
  | { kind: "start"; userId: string; credential: StoredCredential }
  | { kind: "stop"; reason: "anonymous" | "no_membership" }
  | { kind: "pair_needed"; userId: string; pairedByOther: boolean };

export interface SessionCookieWatcher {
  onSessionCookieChanged(callback: () => void): void;
}

export class SessionGate {
  private readonly whoami: WhoamiClient;
  private readonly store: CredentialStore;
  private listeners: Array<(decision: GateDecision) => void> = [];

  constructor(options: { whoami: WhoamiClient; store: CredentialStore }) {
    this.whoami = options.whoami;
    this.store = options.store;
  }

  async evaluate(): Promise<GateDecision> {
    let who: Whoami;
    try {
      who = await this.whoami.whoami();
    } catch {
      // Sin red o sin consola: no hay persona que afirmar. Parar es lo honesto.
      who = { kind: "anonymous" };
    }
    if (who.kind === "anonymous") return { kind: "stop", reason: "anonymous" };
    if (who.kind === "no_membership") return { kind: "stop", reason: "no_membership" };
    const credential = this.store.get(who.userId);
    if (credential) return { kind: "start", userId: who.userId, credential };
    const others = this.store.users().filter((u) => u !== who.userId);
    return { kind: "pair_needed", userId: who.userId, pairedByOther: others.length > 0 };
  }

  onDecision(listener: (decision: GateDecision) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  /** Cada cambio de la cookie de sesión vuelve a preguntar. La caducidad es un cambio más. */
  watch(watcher: SessionCookieWatcher): void {
    watcher.onSessionCookieChanged(() => {
      void this.evaluate().then((decision) => {
        for (const listener of this.listeners) listener(decision);
      });
    });
  }
}
