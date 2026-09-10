/**
 * El único sitio del paquete que toca la red — y ni siquiera él sabe cómo.
 *
 * `Transport` es lo que cada aplicación implementa: la consola con `fetch`
 * contra su BFF (`createFetchTransport`), la aplicación de escritorio con el
 * canal IPC de la cáscara (el renderer no tiene credenciales, así que el
 * proceso principal hace la llamada). `makeCompanionClient` construye encima
 * el mismo cliente que el cajón usaba, con los mismos `Result`.
 *
 * Nunca lanza: cada llamada devuelve un resultado discriminado, porque un
 * cajón que lanza tira la consola entera. `status` y `code` viajan a
 * propósito — la tarjeta de confirmación distingue 409 `action_expired` de
 * 412 `state_changed` (§4.2 del contrato), y el 409 `budget_paused` trae el
 * presupuesto en el cuerpo (§6.2) para no pedirlo otra vez.
 */
import { SseParser } from "./sse";
import type { WireEvent } from "./state";
import type {
  CompanionAction,
  CompanionBudget,
  CompanionDecision,
  CompanionEnabled,
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionThread,
  CompanionThreadRuns,
} from "./wire";

export type Ok<T> = { ok: true; data: T };
export type Err = { ok: false; status: number; detail: string; code: string | null; body: unknown };
export type Result<T> = Ok<T> | Err;

/** Lo que el cajón sabe de dónde está la persona. La consola lo tipa fino. */
export type PageContext = Record<string, unknown> & { client_ref?: string | null };

export type RequestInitLite = { method?: string; body?: string; headers?: Record<string, string> };

export interface Transport {
  request<T>(path: string, init?: RequestInitLite): Promise<Result<T>>;
  /**
   * Sigue el stream de un run desde `sinceSeq`. Resuelve cuando la conexión
   * termina (EOF) y **rechaza** si no se pudo abrir o se cortó: el bucle de
   * reconexión vive en `useCompanion`, no aquí. `signal` aborta la vista,
   * nunca el run (eso es `DELETE /runs/{id}`).
   */
  stream(runId: string, sinceSeq: number, onEvent: (ev: WireEvent) => void, signal: AbortSignal): Promise<void>;
}

/** El transporte de la consola: `fetch` contra `base` (`/api/companion`). */
export function createFetchTransport(base: string, fetchImpl?: typeof fetch): Transport {
  const doFetch = (input: string, init?: RequestInit) => (fetchImpl ?? fetch)(input, init);
  return {
    async request<T>(path: string, init?: RequestInitLite): Promise<Result<T>> {
      try {
        const res = await doFetch(`${base}${path}`, {
          ...init,
          headers: {
            Accept: "application/json",
            ...(init?.body ? { "Content-Type": "application/json" } : {}),
            ...init?.headers,
          },
          cache: "no-store",
        });
        if (res.status === 204) return { ok: true, data: null as T };
        const text = await res.text();
        let body: unknown = null;
        if (text) {
          try {
            body = JSON.parse(text);
          } catch {
            body = text;
          }
        }
        if (!res.ok) {
          const b = body as { detail?: unknown; code?: unknown } | null;
          return {
            ok: false,
            status: res.status,
            detail: b && typeof b.detail === "string" ? b.detail : `HTTP ${res.status}`,
            code: b && typeof b.code === "string" ? b.code : null,
            body,
          };
        }
        return { ok: true, data: body as T };
      } catch {
        // Offline, DNS, aborted — indistinguishable here and all mean the same
        // to the user: we could not reach the Companion.
        return { ok: false, status: 0, detail: "network", code: null, body: null };
      }
    },
    async stream(runId, sinceSeq, onEvent, signal) {
      const url = `${base}/runs/${encodeURIComponent(runId)}/stream?since_seq=${sinceSeq}`;
      const resp = await doFetch(url, { headers: { Accept: "text/event-stream" }, signal, cache: "no-store" });
      if (!resp.ok || !resp.body) throw new Error(`stream ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      const parser = new SseParser();
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        for (const ev of parser.push(decoder.decode(value, { stream: true }))) onEvent(ev);
      }
    },
  };
}

export function makeCompanionClient(transport: Transport) {
  const enc = encodeURIComponent;
  const call = <T,>(path: string, init?: RequestInitLite) => transport.request<T>(path, init);
  return {
    listThreads: (teammateId?: string) =>
      call<CompanionThread[]>(teammateId ? `/threads?teammate_id=${enc(teammateId)}` : "/threads"),
    createThread: (body: { title?: string; client_ref?: string; mode?: "consult" | "build"; teammate_id?: string }) =>
      call<CompanionThread>("/threads", { method: "POST", body: JSON.stringify(body) }),
    patchThread: (id: string, body: { title?: string; archived?: boolean; mode?: "consult" | "build" }) =>
      call<CompanionThread>(`/threads/${enc(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
    /** Runs of a thread, ascending (§5.2) — the source of the run index. */
    threadRuns: (threadId: string) => call<CompanionThreadRuns>(`/threads/${enc(threadId)}/runs`),
    startRun: (threadId: string, prompt: string, pageContext: PageContext | null) =>
      call<CompanionRunStarted>(`/threads/${enc(threadId)}/runs`, {
        method: "POST",
        body: JSON.stringify({ prompt, page_context: pageContext }),
      }),
    runEvents: (runId: string, sinceSeq = 0) =>
      call<CompanionEvents>(`/runs/${enc(runId)}/events?since_seq=${sinceSeq}`),
    /** The ONLY way to stop a run. Aborting the stream does not reach the API. */
    cancelRun: (runId: string) => call<null>(`/runs/${enc(runId)}`, { method: "DELETE" }),
    resumeRun: (runId: string, body: { action_id: string; decision: CompanionDecision; note?: string }) =>
      call<CompanionResumed>(`/runs/${enc(runId)}/resume`, { method: "POST", body: JSON.stringify(body) }),
    getAction: (actionId: string) => call<CompanionAction>(`/actions/${enc(actionId)}`),
    budget: () => call<CompanionBudget>("/budget"),
    /** Per-partner flag of §10 of CONTRACT-V2. The bubble is mounted only
     *  when this is true — an off bubble is ABSENCE, not a disabled button. */
    enabled: () => call<CompanionEnabled>("/enabled"),
  };
}

export type CompanionClient = ReturnType<typeof makeCompanionClient>;
