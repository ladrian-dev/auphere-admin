/**
 * Puente con el dispositivo — Requisito 6.1 y 6.2.
 *
 * **Saliente y sin excepción.** La aplicación abre la conexión hacia la plataforma,
 * sondea trabajo, ejecuta y responde. Nada entra desde internet hacia la máquina del
 * partner: ni puerto a la escucha, ni túnel inverso, ni descubrimiento en red local.
 * Instalar esto no abre un puerto en casa ni en la oficina de nadie.
 *
 * Esta es la razón de que aquí no se importe `node:net` ni `node:http` para servir:
 * `tests/no-inbound.test.ts` recorre el código fuente y falla si aparece cualquier
 * API que escuche. La invariante se comprueba, no se promete.
 *
 * Contrato completo en `specs/001-puesto-trabajo-partner/contracts/device-bridge.md`.
 */

import { HEARTBEAT_INTERVAL_MS } from "./presence.js";

export type Outbound =
  | { kind: "enrol"; platform: "macos" | "windows"; appVersion: string; workdir: string }
  | { kind: "heartbeat"; at: number }
  | { kind: "execution_progress"; executionId: string; at: number }
  | {
      kind: "execution_result";
      executionId: string;
      outcome: "completada" | "expirada" | "terminada" | "denegada";
      exitCode: number | null;
      childrenReaped: number;
    };

export type Inbound =
  | {
      kind: "execute";
      executionId: string;
      executable: string;
      args: string[];
      cwdRelative: string | null;
      timeoutMs: number;
    }
  | { kind: "cancel"; executionId: string };

export type LinkState = "conectando" | "conectado" | "reconectando";

/** Transporte saliente. Solo `send` y `poll`: no hay `listen` porque no puede haberlo. */
export interface OutboundTransport {
  send(message: Outbound): Promise<void>;
  poll(): Promise<Inbound[]>;
}

export interface BridgeOptions {
  transport: OutboundTransport;
  onInbound: (message: Inbound) => Promise<void>;
  /** Inyectable para poder probar la cadencia sin esperar en tiempo real. */
  now?: () => number;
}

export class OutboundBridge {
  private state: LinkState = "conectando";
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly options: BridgeOptions) {}

  get linkState(): LinkState {
    return this.state;
  }

  /** Arranca el latido. La cadencia es la del contrato, no un número suelto aquí. */
  start(): void {
    if (this.timer !== null) return;
    this.timer = setInterval(() => void this.tick(), HEARTBEAT_INTERVAL_MS);
  }

  stop(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  /** Un ciclo: latir, sondear, atender. Si falla, el enlace pasa a `reconectando`. */
  async tick(): Promise<void> {
    const now = this.options.now ?? Date.now;
    try {
      await this.options.transport.send({ kind: "heartbeat", at: now() });
      for (const message of await this.options.transport.poll()) {
        await this.options.onInbound(message);
      }
      this.state = "conectado";
    } catch {
      // §V: `reconectando` es un estado del catálogo, no un error que se pinta en rojo.
      this.state = "reconectando";
    }
  }
}
