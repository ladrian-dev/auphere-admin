/**
 * Cliente de la cola global de aprobaciones — Requisito 11.1.
 *
 * **Cierra T052.** La evaluación estableció que la cola existe y es alcanzable;
 * lo que faltaba era un cliente nuestro que contestara, y construir uno de usar y
 * tirar habría sido trabajo tirado. Éste es el de verdad: vive en la aplicación
 * que el partner instala.
 *
 * **El token se le pide al gateway** (`kirocrew token`). El registro de nonces
 * vive en la memoria de su proceso, así que un token generado aparte devuelve
 * `token superseded` — eso costó una pasada entera de T002 y queda escrito aquí
 * para que nadie lo vuelva a descubrir por su cuenta.
 *
 * **Un fallo no se presenta como cola vacía.** Devolver `[]` cuando la llamada
 * falla diría «no hay nada que aprobar», que es una afirmación distinta —y falsa—
 * de «no he podido preguntar». Es el mismo criterio que en el catálogo.
 */
import type { ApprovalsClient, PendingApproval } from "./app-runtime.js";

type FetchLike = (url: string, init?: { method?: string }) => Promise<{
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}>;

export type GatewayApprovalsOptions = {
  baseUrl: string;
  /** El que emite el gateway. No se genera aparte. */
  token: string;
  fetch?: FetchLike;
};

export class ApprovalsUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApprovalsUnavailable";
  }
}

export class GatewayApprovals implements ApprovalsClient {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetch: FetchLike;

  constructor(options: GatewayApprovalsOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token;
    this.fetch = options.fetch ?? (globalThis.fetch as unknown as FetchLike);
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}?token=${encodeURIComponent(this.token)}`;
  }

  async pending(): Promise<PendingApproval[]> {
    const response = await this.fetch(this.url("/api/approvals"));
    if (!response.ok) {
      throw new ApprovalsUnavailable(
        `no se pudo leer la cola de aprobaciones (HTTP ${response.status})`,
      );
    }
    const body = (await response.json()) as unknown;
    return Array.isArray(body) ? (body as PendingApproval[]) : [];
  }

  async answer(id: string, allow: boolean): Promise<boolean> {
    const action = allow ? "approve" : "deny";
    const response = await this.fetch(
      this.url(`/api/approvals/${encodeURIComponent(id)}/${action}`),
      { method: "POST" },
    );
    if (!response.ok) {
      throw new ApprovalsUnavailable(
        `el gateway rechazó la respuesta a ${id} (HTTP ${response.status})`,
      );
    }
    return true;
  }
}
