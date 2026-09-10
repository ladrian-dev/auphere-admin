/**
 * El proceso principal habla con la plataforma **como la persona** — spec 003, D9.
 *
 * `fetch` es el de la partición humana (`session.fromPartition(...).fetch`),
 * inyectado: lleva la cookie de la consola sin que nadie de aquí la vea. Cada
 * respuesta pasa por `redact` antes de salir hacia el renderer. Un 401 o un
 * 403 `no_membership` no son errores: son «sin sesión», y se dicen como tal.
 */
import { redact } from "./app-ipc.js";
import { type SseEvent, readSse } from "./sse.js";

export type Ok<T> = { ok: true; data: T };
export type Err = { ok: false; status: number; detail: string; code: string | null; body: unknown };
export type Result<T> = Ok<T> | Err;

export class SessionLost extends Error {
  constructor(readonly reason: "anonymous" | "no_membership") {
    super(`sesión perdida: ${reason}`);
    this.name = "SessionLost";
  }
}

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export type PlatformClientOptions = {
  /** Origen de la consola (`https://console.auphere.com`). */
  consoleUrl: string;
  /** El `fetch` de la partición de la persona. Nunca el global. */
  fetch: FetchLike;
};

export class PlatformClient {
  private readonly origin: string;
  private readonly fetch: FetchLike;

  constructor(options: PlatformClientOptions) {
    this.origin = new URL(options.consoleUrl).origin;
    this.fetch = options.fetch;
  }

  /** `GET /api/...` del BFF, o `POST`/`PATCH`/`DELETE` con cuerpo JSON. */
  async request<T>(path: string, init?: { method?: string; body?: unknown }): Promise<Result<T>> {
    let res: Response;
    try {
      res = await this.fetch(`${this.origin}${path}`, {
        method: init?.method ?? "GET",
        headers: {
          Accept: "application/json",
          ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        ...(init?.body !== undefined ? { body: JSON.stringify(init.body) } : {}),
        cache: "no-store",
        redirect: "manual",
      });
    } catch {
      return { ok: false, status: 0, detail: "network", code: null, body: null };
    }
    // El proxy de la consola manda a `/login` a quien no tiene sesión: una
    // redirección o una página no son datos — son «sin sesión».
    if (res.status === 401 || res.status === 302 || res.status === 307) throw new SessionLost("anonymous");
    if (res.status === 204) return { ok: true, data: null as T };
    const text = await res.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        if (!res.ok) throw new SessionLost("anonymous");
        body = null;
      }
    }
    if (res.status === 403 && (body as { code?: string } | null)?.code === "no_membership") {
      throw new SessionLost("no_membership");
    }
    if (!res.ok) {
      const b = body as { detail?: unknown; code?: unknown } | null;
      return redact({
        ok: false,
        status: res.status,
        detail: b && typeof b.detail === "string" ? b.detail : `HTTP ${res.status}`,
        code: b && typeof b.code === "string" ? b.code : null,
        body,
      });
    }
    return { ok: true, data: redact(body as T) };
  }

  /** Un SSE del BFF, leído hasta el final. Rechaza si no se pudo abrir. */
  async stream(path: string, signal: AbortSignal, onEvent: (ev: SseEvent) => void): Promise<void> {
    const res = await this.fetch(`${this.origin}${path}`, {
      headers: { Accept: "text/event-stream" },
      signal,
      cache: "no-store",
      redirect: "manual",
    });
    if (res.status === 401 || res.status === 302 || res.status === 307) throw new SessionLost("anonymous");
    if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
    await readSse(res.body, (ev) => onEvent(redact(ev)));
  }
}
