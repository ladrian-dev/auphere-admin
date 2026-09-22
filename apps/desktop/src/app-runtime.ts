/**
 * El ciclo de vida de la aplicación de escritorio — 001-R15, 6 y 12; spec 002.
 *
 * Junta lo que hasta ahora eran piezas sueltas: el puente saliente, la
 * presencia, la barra, la credencial y la puerta de sesión. La ventana de
 * Electron es pegamento fino sobre esto; **lo que decide vive aquí**, que es lo
 * que se puede probar sin un display.
 *
 * **El orden de arranque importa y por eso está fijado.** Primero se comprueba
 * el aislamiento de sesión (15.3) y solo después se abre el puente.
 *
 * Con la spec 002 la máquina ya no lleva una credencial por variable de entorno:
 * la **canjea** con un código (`pair`), la guarda cifrada por persona, la renueva
 * sola antes de que caduque, la olvida al desemparejar, y **solo late con una
 * persona dentro** (11.1): sin sesión no hay quien apruebe.
 */
import { OutboundBridge, type Inbound, type LinkState, type OutboundTransport } from "./bridge.js";
import { TaskFiles } from "./task-files.js";
import {
  initialState,
  localToolsOffered as barOffersTools,
  transition,
  type BarEvent,
  type BarLink,
  type BarState,
} from "./workstation-state.js";
import type { CredentialStore, StoredCredential } from "./credential-store.js";
import { declareDirectory, type DirectoryFs } from "./directory-declare.js";
import { AppUpdateRequired, BridgeRejected, type HttpTransport, type PolledLink } from "./http-transport.js";
import { localToolsAvailable, statusLabel, type StatusLabel } from "./link-state.js";
import { runExecuteMessage } from "./local-runner.js";
import { derivePresence, type Presence } from "./presence.js";
import { assertPartitionsAreSeparate } from "./session-isolation.js";
import type { GateDecision } from "./session-gate.js";

export type PendingApproval = { id: string; prompt: string };

/** No hay persona dentro para la que contestar: no se contesta por otra (R5.3). */
export class ApprovalsNotForThisPerson extends Error {
  constructor() {
    super("no hay sesión de la persona dueña de esta máquina: no se contestan aprobaciones");
    this.name = "ApprovalsNotForThisPerson";
  }
}

/** Cliente de la cola global de aprobaciones. */
export interface ApprovalsClient {
  pending(): Promise<PendingApproval[]>;
  answer(id: string, allow: boolean): Promise<boolean>;
}

/**
 * Lo que el transporte v2 sabe hacer además de latir y sondear.
 *
 * Tenía un `pair` que canjeaba el código; la spec 012 lo retiró con el
 * endpoint. El alta de la máquina **no pasa por aquí**: va del proceso
 * principal al BFF con la cookie de la partición humana, que es el único sitio
 * donde esa cookie existe.
 */
export interface IdentityTransport extends OutboundTransport {
  renew: HttpTransport["renew"];
  declareLink: HttpTransport["declareLink"];
  pollAll: HttpTransport["pollAll"];
  useToken: HttpTransport["useToken"];
}

/** Renovar cuando quede menos de esto (contrato: 6 h de 12). */
export const RENEW_BEFORE_MS = 6 * 60 * 60 * 1000;

export type AppRuntimeOptions = {
  consoleUrl: string;
  /** Directorio de repliegue (001). Con la 002 el directorio es por cliente. */
  workdir?: string;
  transport: OutboundTransport | IdentityTransport;
  approvals: ApprovalsClient;
  now?: () => number;
  /** Spec 002. Opcionales para que la 001 siga arrancando igual. */
  store?: CredentialStore;
  machine?: { hostname: string; platform: "macos" | "windows" };
  fs?: DirectoryFs;
  /**
   * Registrar esta máquina con la sesión (spec 012, R3.1).
   *
   * Opcional para que lo que ya existe siga arrancando igual: sin esto, la
   * aplicación se comporta como antes y espera el código.
   */
  registerMachine?: (facts: {
    hostname: string;
    platform: "macos" | "windows";
    installId: string;
  }) => Promise<RegisterOutcome>;
  /** Qué instalación es ésta. Sobrevive a desemparejar. */
  installId?: string;
};

/** Lo que puede pasar al registrar, y a dónde lleva cada cosa. */
export type RegisterOutcome =
  | {
      kind: "registered";
      machine: {
        deviceId: string;
        credential: string;
        generation: number;
        expiresAt: string;
        partnerSlug: string;
        displayName: string;
      };
    }
  | { kind: "sign_in_again" }
  | { kind: "at_cap" }
  | { kind: "unavailable" };

/**
 * Qué se le dice a la persona cuando registrar no sale (spec 012, R3).
 *
 * Tres motivos y tres caminos distintos: entrar de nuevo, retirar una máquina,
 * o esperar. La API los uniforma porque al otro lado puede haber un
 * desconocido; aquí no lo hay, y decir «no se pudo» a secas dejaría a la
 * persona sin saber qué hacer.
 */
const REGISTER_FAILURES: Record<"sign_in_again" | "at_cap" | "unavailable", string> = {
  sign_in_again: "register_sign_in_again",
  at_cap: "register_at_cap",
  unavailable: "register_unavailable",
};

/**
 * Se preguntaba por `pair`, que ya no existe. Ahora por `renew`: es la
 * operación que **solo** tiene el transporte v2 y la que el runtime de verdad
 * necesita de él, así que distingue lo mismo sin depender de un método muerto.
 */
function hasIdentity(t: OutboundTransport | IdentityTransport): t is IdentityTransport {
  return typeof (t as IdentityTransport).renew === "function";
}

export class AppRuntime {
  readonly consoleUrl: string;
  private readonly workdir: string | undefined;
  private readonly approvals: ApprovalsClient;
  private readonly bridge: OutboundBridge;
  private readonly transport: OutboundTransport | IdentityTransport;
  private readonly store: CredentialStore | undefined;
  private readonly machine: { hostname: string; platform: "macos" | "windows" } | undefined;
  private readonly fs: DirectoryFs | undefined;
  private readonly registerMachine: AppRuntimeOptions["registerMachine"];
  private readonly installId: string | undefined;
  private readonly now: () => number;
  private lastHeartbeatAt: number | null = null;
  private bar: BarState;
  private barListeners: Array<(state: BarState) => void> = [];
  /**
   * Quién quiere enterarse de que la credencial guardada cambió.
   *
   * Existe porque hay **dos superficies** contando el mismo hecho y solo una se
   * enteraba: la barra se mueve con los eventos del puente, pero el banner de la
   * pantalla lo pinta `SessionGate`, que deriva su veredicto del almacén. Antes,
   * emparejar cambiaba el almacén sin tocar la cookie ni perder la sesión, así
   * que nada volvía a preguntarle a la puerta y el banner seguía diciendo «sin
   * emparejar» con la barra ya conectada.
   *
   * **Se anuncia, no se decide.** El runtime no conoce la puerta y no debe: dice
   * que la credencial cambió, y quien mande decide qué hacer con eso.
   */
  private identityListeners: Array<() => void> = [];
  private userId: string | null = null;
  private credential: StoredCredential | null = null;
  private links: PolledLink[] = [];
  private running = false;

  /** Ganchos de diagnóstico; la ventana los usa para pintar. */
  onIsolationChecked?: () => void;
  /** Solo para pruebas: fuerza una configuración de particiones rota. */
  forceBrokenIsolation = false;

  constructor(options: AppRuntimeOptions) {
    this.consoleUrl = options.consoleUrl;
    this.workdir = options.workdir;
    this.approvals = options.approvals;
    this.transport = options.transport;
    this.store = options.store;
    this.machine = options.machine;
    this.fs = options.fs;
    this.registerMachine = options.registerMachine;
    this.installId = options.installId;
    this.now = options.now ?? Date.now;
    this.bar = initialState(options.store ? options.store.encryptionAvailable : true);
    this.bridge = new OutboundBridge({
      transport: options.transport,
      onInbound: (message) => this.handle(message),
      now: options.now,
    });
  }

  // ── lo que había (001) ──────────────────────────────────────────────────

  get linkState(): LinkState {
    return this.bridge.linkState;
  }

  get presence(): Presence {
    return derivePresence(this.lastHeartbeatAt, this.now());
  }

  /** Arranca. **Comprueba el aislamiento antes de abrir nada.** */
  async start(): Promise<void> {
    if (this.forceBrokenIsolation) {
      assertPartitionsAreSeparate("persist:x", "persist:x");
    }
    assertPartitionsAreSeparate();
    this.onIsolationChecked?.();
    this.running = true;
    await this.tick();
  }

  /** Detiene el latido **sin** olvidar la credencial (11.1). */
  stop(): void {
    this.running = false;
    this.lastHeartbeatAt = null;
  }

  /** Un ciclo del puente. La ventana lo llama con la cadencia del latido. */
  async tick(): Promise<void> {
    if (!this.running) return;
    await this.maybeRenew();
    try {
      await this.bridge.tick();
    } catch {
      // OutboundBridge ya tradujo el fallo a `reconectando`.
    }
    if (this.bridge.linkState === "conectado") {
      this.lastHeartbeatAt = this.now();
      this.setBar({ kind: "link_ok" });
      await this.refreshLinks();
    } else {
      this.lastHeartbeatAt = null;
      await this.inspectFailure();
    }
  }

  /** Lo que se pinta. Nunca es un error: ver `link-state.ts`. */
  status(): StatusLabel {
    return statusLabel(this.bridge.linkState);
  }

  /** Hacen falta puente **y** dispositivo — y, con la 002, la barra en `conectada`. */
  localToolsOffered(): boolean {
    const bridgeOk = localToolsAvailable(this.bridge.linkState, this.presence);
    if (!this.store) return bridgeOk; // arranque de la 001, sin barra
    return bridgeOk && barOffersTools(this.bar.status);
  }

  /**
   * Las aprobaciones que contesta esta aplicación son las de la persona con
   * sesión (R5.3, Historia 5). Con la spec 002 el puente solo corre para ella;
   * si no corre, **no se pregunta** — devolver `[]` diría «no hay nada que
   * aprobar», que es distinto y falso (§V).
   */
  pendingApprovals(): Promise<PendingApproval[]> {
    if (this.store && !this.running) {
      return Promise.reject(new ApprovalsNotForThisPerson());
    }
    return this.approvals.pending();
  }

  answerApproval(id: string, allow: boolean): Promise<boolean> {
    if (this.store && !this.running) {
      return Promise.reject(new ApprovalsNotForThisPerson());
    }
    return this.approvals.answer(id, allow);
  }

  // ── la barra (spec 002) ─────────────────────────────────────────────────

  get barState(): BarState {
    return this.bar;
  }

  /** Los clientes de esta máquina **con su directorio** (R11.1).
   *
   *  La barra no lo lleva a propósito —su contrato es de estado, no de rutas—,
   *  y el panel de entorno sí lo necesita: sin directorio, «dónde trabaja» no
   *  se puede contestar. No sale de esta máquina: la plataforma ya sabe que hay
   *  un directorio declarado, nunca cuál. */
  get clientLinks(): ReadonlyArray<{ clientRef: string; clientName: string | null; workdir: string | null }> {
    return this.links.map((l) => ({
      clientRef: l.clientRef,
      clientName: l.clientName ?? null,
      workdir: l.workdir ?? null,
    }));
  }

  /** Se dispara cuando la credencial guardada cambia: al canjear y al olvidar. */
  onIdentityChanged(listener: () => void): () => void {
    this.identityListeners.push(listener);
    return () => {
      this.identityListeners = this.identityListeners.filter((l) => l !== listener);
    };
  }

  private announceIdentityChanged(): void {
    for (const listener of this.identityListeners) listener();
  }

  onBarState(listener: (state: BarState) => void): () => void {
    this.barListeners.push(listener);
    return () => {
      this.barListeners = this.barListeners.filter((l) => l !== listener);
    };
  }

  private setBar(event: BarEvent): void {
    const next = transition(this.bar, event);
    if (next === this.bar) return;
    this.bar = next;
    for (const listener of this.barListeners) listener(next);
  }

  /** La puerta de sesión decidió. Es la única forma de arrancar el puente con la 002. */
  async applyGate(decision: GateDecision): Promise<void> {
    // Spec 010 R3.2: no se pudo preguntar. No se para el puente ni se olvida
    // nada — conservar lo último que se supo es justamente el arreglo.
    if (decision.kind === "unconfirmed") return;
    if (decision.kind === "stop") {
      this.stop();
      this.userId = null;
      this.credential = null;
      this.setBar({ kind: "session_gone" });
      return;
    }
    this.userId = decision.userId;
    this.setBar({ kind: "person", locale: decision.locale });
    if (decision.kind === "pair_needed") {
      this.stop();
      this.credential = null;
      // Spec 012, R3.1: entrar deja la máquina lista. Antes de anunciar «sin
      // emparejar» se intenta registrarla con la sesión que acabamos de
      // confirmar — para eso servía el código, y la sesión ya lo demuestra.
      if (await this.registerWithSession()) return;
      this.setBar(decision.pairedByOther ? { kind: "session_other_person" } : { kind: "unpaired" });
      return;
    }
    this.credential = decision.credential;
    if (hasIdentity(this.transport)) this.transport.useToken(decision.credential.token);
    this.setBar({
      kind: "restored",
      machine: { displayName: decision.credential.displayName, hostname: this.machine?.hostname ?? "" },
    });
    if (!this.running) await this.start();
    else this.setBar({ kind: "session_same_person" });
  }

  /**
   * Registra esta máquina con la sesión recién confirmada (spec 012, R3.1).
   *
   * Devuelve `true` si quedó lista, y entonces quien llama no tiene que
   * anunciar nada: la máquina arranca sola.
   *
   * **Los tres fallos se distinguen a propósito**, porque llevan a cosas
   * distintas: volver a entrar, retirar una máquina, o esperar. Uniformarlos
   * —que es lo que hace la API con el desconocido del otro lado— aquí dejaría a
   * la persona sin saber qué hacer, y quien pregunta ya está dentro.
   */
  private async registerWithSession(): Promise<boolean> {
    if (!this.registerMachine || !this.installId || !this.machine || !this.store || !this.userId) {
      return false;
    }
    this.setBar({ kind: "pair_started" });
    const outcome = await this.registerMachine({
      hostname: this.machine.hostname,
      platform: this.machine.platform,
      installId: this.installId,
    });
    if (outcome.kind !== "registered") {
      this.setBar({ kind: "pair_failed", code: REGISTER_FAILURES[outcome.kind] });
      return false;
    }

    const credential: StoredCredential = {
      deviceId: outcome.machine.deviceId,
      token: outcome.machine.credential,
      generation: outcome.machine.generation,
      expiresAt: outcome.machine.expiresAt,
      partnerSlug: outcome.machine.partnerSlug,
      displayName: outcome.machine.displayName,
    };
    this.store.put(this.userId, credential);
    this.credential = credential;
    if (hasIdentity(this.transport)) this.transport.useToken(credential.token);
    this.setBar({
      kind: "pair_ok",
      machine: { displayName: credential.displayName, hostname: this.machine.hostname },
    });
    this.announceIdentityChanged();
    if (!this.running) await this.start();
    return true;
  }

  /**
   * Cómo se inicia sesión de verdad — spec 009, 2ª enmienda.
   *
   * Se inyecta porque al otro lado hay un oyente en loopback, un navegador del
   * sistema y el `fetch` de una partición de Electron; y el runtime se prueba
   * sin nada de eso. Aquí sólo vive **qué pasa después**.
   */
  private signIn: (() => Promise<{ ok: boolean }>) | null = null;

  useBrowserSignIn(fn: () => Promise<{ ok: boolean }>): void {
    this.signIn = fn;
  }

  /**
   * Inicia sesión abriendo el navegador — spec 009, 2ª enmienda (RFC 8252).
   *
   * **Este método hace muy poco a propósito.** Ni genera el PKCE, ni levanta el
   * oyente, ni ve ningún token: pide que ocurra y, si sale bien, anuncia que la
   * identidad cambió para que la puerta vuelva a derivar el veredicto.
   *
   * Y desde la spec 012 ese veredicto hace más: si la máquina no está
   * registrada, `applyGate` la registra con la sesión que acaba de confirmarse.
   * Entrar deja la máquina lista, que era el trabajo del código retirado.
   *
   * Que falle no es una avería: cerrar la pestaña del navegador es una decisión
   * y se cuenta como estado, nunca en rojo.
   */
  async signInWithBrowser(): Promise<void> {
    if (!this.signIn) {
      this.setBar({ kind: "redeem_failed" });
      return;
    }
    let ok = false;
    try {
      ok = (await this.signIn()).ok;
    } catch {
      ok = false;
    }
    if (!ok) {
      this.setBar({ kind: "redeem_failed" });
      return;
    }
    this.announceIdentityChanged();
  }

  /** Desemparejar: olvida la credencial. Archivar es de la consola (R11.2). */
  unpair(): void {
    this.stop();
    if (this.store && this.userId) this.store.forget(this.userId);
    this.credential = null;
    this.links = [];
    this.setBar({ kind: "unpaired" });
    this.announceIdentityChanged();
  }

  /** Declarar el directorio de un cliente con el selector nativo (R7). */
  async declareDirectory(clientRef: string, pick: () => Promise<string | null>) {
    if (!hasIdentity(this.transport) || !this.fs) return { kind: "cancelled" as const };
    const result = await declareDirectory({ clientRef, pick, fs: this.fs, transport: this.transport });
    if (result.kind === "declared") await this.refreshLinks();
    return result;
  }

  /** El directorio de un cliente vinculado, o el de repliegue (001). */
  /** Lo que los comandos nombraron, por tarea (R11.2). Vive en RAM y se pierde
   *  al cerrar: es contexto de lo que acaba de pasar, no un histórico. */
  readonly taskFiles = new TaskFiles();

  workdirFor(clientRef: string | undefined): string | null {
    if (clientRef) {
      const link = this.links.find((l) => l.clientRef === clientRef);
      return link?.workdir ?? null;
    }
    return this.workdir ?? null;
  }

  // ── internos ────────────────────────────────────────────────────────────

  private async refreshLinks(): Promise<void> {
    if (!hasIdentity(this.transport)) return;
    try {
      const polled = await this.transport.pollAll();
      this.links = polled.links;
      const links: BarLink[] = polled.links.map((l) => ({
        clientRef: l.clientRef,
        clientName: l.clientName,
        needsDirectory: l.needsDirectory,
        // R8.4: dónde trabaja, para poder enseñarlo al declarar. No sube a la
        // plataforma más allá de lo que `declareLink` ya manda.
        workdir: l.workdir,
      }));
      this.setBar({ kind: "links_updated", links });
    } catch (error) {
      await this.translate(error);
    }
  }

  private async inspectFailure(): Promise<void> {
    // OutboundBridge se traga la causa para quedarse en `reconectando`; aquí se
    // vuelve a preguntar una vez para distinguir un rechazo de un fallo.
    if (!hasIdentity(this.transport)) {
      this.setBar({ kind: "link_lost" });
      return;
    }
    try {
      await this.transport.send({ kind: "heartbeat", at: this.now() });
    } catch (error) {
      await this.translate(error);
      return;
    }
    this.setBar({ kind: "link_lost" });
  }

  private async translate(error: unknown): Promise<void> {
    // Spec 008: va ANTES de `BridgeRejected` y no dentro. La credencial está
    // bien; lo viejo es el binario. Se para el puente y se dice, pero **no se
    // olvida nada**: si esto borrara la credencial, exigir una versión mínima
    // desemparejaría a todo el mundo a la vez.
    if (error instanceof AppUpdateRequired) {
      this.stop();
      this.setBar({ kind: "version_rejected", minimumVersion: error.minimumVersion });
      return;
    }
    if (error instanceof BridgeRejected) {
      this.stop();
      if (this.store && this.userId) this.store.forget(this.userId);
      this.credential = null;
      if (error.reason === "device_archived") this.setBar({ kind: "archived" });
      else this.setBar({ kind: error.reason === "pairing_required" ? "pairing_required" : "unauthorized" });
      return;
    }
    this.setBar({ kind: "link_lost" });
  }

  private async maybeRenew(): Promise<void> {
    if (!hasIdentity(this.transport) || !this.store || !this.userId || !this.credential) return;
    const remaining = Date.parse(this.credential.expiresAt) - this.now();
    if (Number.isNaN(remaining) || remaining > RENEW_BEFORE_MS) return;
    try {
      const renewed = await this.transport.renew();
      this.credential = {
        ...this.credential,
        token: renewed.credential,
        generation: renewed.generation,
        expiresAt: renewed.expiresAt,
      };
      this.store.put(this.userId, this.credential);
    } catch (error) {
      await this.translate(error);
    }
  }

  private async handle(message: Inbound): Promise<void> {
    if (message.kind !== "execute") return;
    const workdir = this.workdirFor(message.clientRef);
    if (workdir === null) return; // sin directorio declarado no hay dónde ejecutar (7.5)
    // Lo que este comando nombró, para el panel de entorno (R11.2). Se anota
    // **antes** de ejecutar: aunque el comando falle, nombró lo que nombró.
    this.taskFiles.record({
      taskId: message.taskId ?? null,
      clientRef: message.clientRef ?? "",
      executable: message.executable,
      args: message.args,
      cwdRelative: message.cwdRelative,
      workdir,
    });
    const result = await runExecuteMessage(message, workdir);
    // **Y se contesta.** Hasta la spec 003 el resultado se calculaba y se
    // tiraba: no había quien pusiera trabajo en la cola, así que nunca se
    // notó. Ahora hay alguien esperándolo al otro lado, y un asiento de
    // auditoría que se quedaría abierto para siempre si no se cerrara.
    try {
      await this.transport.send(result);
    } catch (error) {
      await this.translate(error);
    }
  }
}
