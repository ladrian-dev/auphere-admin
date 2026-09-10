/**
 * El `Transport` de `@nexus/companion-ui` sobre IPC (spec 003, D9/D11).
 *
 * `useCompanion` habla en rutas (`POST /threads/{id}/runs`); aquí cada ruta se
 * traduce a **un** canal de la lista — no hay un canal genérico que reenvíe
 * rutas al principal. Lo que no está en la lista se contesta como 404, sin
 * inventar nada.
 */
import type { Result, Transport, WireEvent } from "@nexus/companion-ui";

import { bridge } from "./bridge";

const notHere = <T,>(): Result<T> => ({ ok: false, status: 404, detail: "not_available_in_app", code: null, body: null });

function route<T>(path: string, method: string, body: unknown): Promise<Result<T>> {
  const url = new URL(path, "http://ipc");
  const [, head, id, tail] = url.pathname.split("/");
  const b = (body ?? {}) as Record<string, unknown>;
  const as = (p: Promise<unknown>) => p as Promise<Result<T>>;
  if (head === "threads" && !id && method === "POST") {
    return as(bridge.threadOpen({ teammate_id: String(b.teammate_id) }).then((r) => (r.ok ? { ok: true, data: { id: r.data.thread_id } } : r)));
  }
  if (head === "threads" && id && tail === "runs" && method === "GET") return as(bridge.threadRuns({ thread_id: id }));
  if (head === "threads" && id && tail === "runs" && method === "POST") {
    const ctx = b.page_context as { client_ref?: string } | null | undefined;
    return as(bridge.threadSend({ thread_id: id, text: String(b.prompt), ...(ctx?.client_ref ? { client_ref: ctx.client_ref } : {}) }));
  }
  if (head === "runs" && id && tail === "events" && method === "GET") {
    return as(bridge.runEvents({ run_id: id, since_seq: Number(url.searchParams.get("since_seq") ?? 0) }));
  }
  if (head === "runs" && id && !tail && method === "DELETE") return as(bridge.threadCancel({ run_id: id }));
  if (head === "runs" && id && tail === "resume" && method === "POST") {
    return as(bridge.inboxDecide({ action_id: String(b.action_id), run_id: id, decision: String(b.decision), ...(b.note ? { note: String(b.note) } : {}) }));
  }
  if (head === "budget" && method === "GET") return as(bridge.usage().then((r) => (r.ok ? { ok: true, data: r.data.budget } : r)));
  return Promise.resolve(notHere<T>());
}

export const ipcTransport: Transport = {
  request<T>(path: string, init?: { method?: string; body?: string }): Promise<Result<T>> {
    const body = init?.body ? (JSON.parse(init.body) as unknown) : undefined;
    return route<T>(path, init?.method ?? "GET", body);
  },
  stream(runId: string, sinceSeq: number, onEvent: (ev: WireEvent) => void, signal: AbortSignal): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      let streamId: string | null = null;
      let settled = false;
      const offEvent = bridge.on("app:event", (p) => {
        if (p.stream_id === streamId) onEvent(p.event);
      });
      const offEnd = bridge.on("app:stream.end", (p) => {
        if (p.stream_id !== streamId || settled) return;
        settled = true;
        offEvent();
        offEnd();
        if (p.ok) resolve();
        else reject(new Error("stream"));
      });
      signal.addEventListener("abort", () => {
        if (streamId) void bridge.streamClose({ stream_id: streamId });
        if (!settled) {
          settled = true;
          offEvent();
          offEnd();
          resolve();
        }
      });
      void bridge.streamOpen({ run_id: runId, since_seq: sinceSeq }).then(
        (r) => {
          streamId = r.stream_id;
          if (signal.aborted) void bridge.streamClose({ stream_id: r.stream_id });
        },
        (err: unknown) => {
          if (!settled) {
            settled = true;
            offEvent();
            offEnd();
            reject(err instanceof Error ? err : new Error("stream"));
          }
        },
      );
    });
  },
};
