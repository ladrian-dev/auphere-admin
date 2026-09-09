/**
 * El ciclo de vida de la aplicación de escritorio — Requisitos 15, 6 y 12.
 *
 * Junta lo que hasta ahora eran piezas sueltas: el puente saliente, la presencia,
 * el estado del enlace y las aprobaciones. La ventana de Electron es pegamento
 * fino sobre esto; **lo que decide vive aquí**, que es lo que se puede probar sin
 * un display.
 *
 * **El orden de arranque importa y por eso está fijado.** Primero se comprueba el
 * aislamiento de sesión (15.3) y solo después se abre el puente: al revés, una
 * configuración rota abriría la conexión antes de que nadie se enterara, y lo que
 * queda al otro lado es la sesión de una persona en la misma máquina que un
 * agente que ejecuta comandos.
 */
import { OutboundBridge, type Inbound, type LinkState, type OutboundTransport } from "./bridge.js";
import { localToolsAvailable, statusLabel, type StatusLabel } from "./link-state.js";
import { runExecuteMessage } from "./local-runner.js";
import { derivePresence, type Presence } from "./presence.js";
import { assertPartitionsAreSeparate } from "./session-isolation.js";

export type PendingApproval = { id: string; prompt: string };

/** Cliente de la cola global de aprobaciones. */
export interface ApprovalsClient {
  pending(): Promise<PendingApproval[]>;
  answer(id: string, allow: boolean): Promise<boolean>;
}

export type AppRuntimeOptions = {
  consoleUrl: string;
  workdir: string;
  transport: OutboundTransport;
  approvals: ApprovalsClient;
  now?: () => number;
};

export class AppRuntime {
  readonly consoleUrl: string;
  private readonly workdir: string;
  private readonly approvals: ApprovalsClient;
  private readonly bridge: OutboundBridge;
  private lastHeartbeatAt: number | null = null;

  /** Ganchos de diagnóstico; la ventana los usa para pintar. */
  onIsolationChecked?: () => void;
  /** Solo para pruebas: fuerza una configuración de particiones rota. */
  forceBrokenIsolation = false;

  constructor(options: AppRuntimeOptions) {
    this.consoleUrl = options.consoleUrl;
    this.workdir = options.workdir;
    this.approvals = options.approvals;
    this.bridge = new OutboundBridge({
      transport: options.transport,
      onInbound: (message) => this.handle(message),
      now: options.now,
    });
  }

  get linkState(): LinkState {
    return this.bridge.linkState;
  }

  get presence(): Presence {
    return derivePresence(this.lastHeartbeatAt, Date.now());
  }

  /** Arranca. **Comprueba el aislamiento antes de abrir nada.** */
  async start(): Promise<void> {
    if (this.forceBrokenIsolation) {
      assertPartitionsAreSeparate("persist:x", "persist:x");
    }
    assertPartitionsAreSeparate();
    this.onIsolationChecked?.();
    await this.bridge.tick();
    if (this.bridge.linkState === "conectado") this.lastHeartbeatAt = Date.now();
  }

  /** Un ciclo del puente. La ventana lo llama con la cadencia del latido. */
  async tick(): Promise<void> {
    await this.bridge.tick();
    this.lastHeartbeatAt = this.bridge.linkState === "conectado" ? Date.now() : null;
  }

  /** Lo que se pinta. Nunca es un error: ver `link-state.ts`. */
  status(): StatusLabel {
    return statusLabel(this.bridge.linkState);
  }

  /** Hacen falta puente **y** dispositivo. */
  localToolsOffered(): boolean {
    return localToolsAvailable(this.bridge.linkState, this.presence);
  }

  pendingApprovals(): Promise<PendingApproval[]> {
    return this.approvals.pending();
  }

  /**
   * Contesta una aprobación **por la cola global**, que es la superficie que el
   * sustrato sabe leer. No es un prompt local: un sí que solo existe en esta
   * ventana no desbloquea a nadie.
   */
  answerApproval(id: string, allow: boolean): Promise<boolean> {
    return this.approvals.answer(id, allow);
  }

  private async handle(message: Inbound): Promise<void> {
    if (message.kind !== "execute") return;
    await runExecuteMessage(message, this.workdir);
  }
}
