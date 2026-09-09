/**
 * El transporte real del puente — Requisitos 6.1 y 6.2. Cierra el recorrido.
 *
 * **Solo sale.** Los tres verbos son salientes: latir, sondear y devolver
 * resultado. No hay `listen` ni nada que se le parezca, y hay un test que lo
 * afirma — porque la promesa de que instalar esto no abre un puerto en casa de
 * nadie se rompería en silencio el día que alguien añada uno «para depurar».
 *
 * **Un fallo se levanta, no se convierte en silencio.** Si el sondeo devolviera
 * `[]` cuando la llamada falla, el puente diría «no hay trabajo» — que es
 * distinto, y falso, de «no he podido preguntar». `OutboundBridge` cuenta con esa
 * excepción para pasar a `reconectando`; tragársela lo dejaría en `conectado`
 * eternamente, enseñando un estado que no es.
 */
import type { Inbound, Outbound, OutboundTransport } from "./bridge.js";

type FetchLike = (
  url: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

export type HttpTransportOptions = {
  baseUrl: string;
  /** La credencial del dispositivo, entregada una sola vez en el alta. */
  token: string;
  fetch?: FetchLike;
};

export class BridgeUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BridgeUnavailable";
  }
}

export class HttpTransport implements OutboundTransport {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetch: FetchLike;

  constructor(options: HttpTransportOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token;
    this.fetch = options.fetch ?? (globalThis.fetch as unknown as FetchLike);
  }

  private get headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" };
  }

  async send(message: Outbound): Promise<void> {
    const [path, body] = this.encode(message);
    if (path === null) return; // progreso: no viaja todavía, y callarse es correcto
    const response = await this.fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new BridgeUnavailable(`${path} respondió ${response.status}`);
    }
  }

  async poll(): Promise<Inbound[]> {
    const response = await this.fetch(`${this.baseUrl}/device/poll`, {
      method: "GET",
      headers: this.headers,
    });
    if (!response.ok) {
      throw new BridgeUnavailable(`/device/poll respondió ${response.status}`);
    }
    const body = (await response.json()) as { work?: Inbound[] };
    return Array.isArray(body.work) ? body.work : [];
  }

  /** Traduce el mensaje del contrato al cuerpo que espera la API. */
  private encode(message: Outbound): [string | null, Record<string, unknown>] {
    switch (message.kind) {
      case "heartbeat":
        return ["/device/heartbeat", {}];
      case "enrol":
        return ["/device/heartbeat", { app_version: message.appVersion }];
      case "execution_result":
        return [
          "/device/result",
          {
            execution_id: message.executionId,
            outcome: message.outcome,
            exit_code: message.exitCode,
            children_reaped: message.childrenReaped,
          },
        ];
      case "execution_progress":
        return [null, {}];
    }
  }
}
