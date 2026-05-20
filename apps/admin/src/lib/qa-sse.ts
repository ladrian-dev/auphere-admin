/**
 * Typed SSE client for the QA Playground stream (ADR-021 Fase 1).
 *
 * Wraps the browser's ``EventSource`` and dispatches each backend
 * event to a typed handler. The wire protocol is defined in
 * ``apps/api/src/nexus_api/api/qa_streaming.py`` — keep these
 * discriminated union types in sync with the translator there.
 *
 * Resume strategy (matches the spec in
 * ``features/qa-playground-streaming-implementation.md``):
 *   - Track the last seen ``seq`` from the ``id:`` field of every
 *     event the server emits.
 *   - On reconnect, append ``?since_seq=<lastSeq>`` to the URL so the
 *     server replays buffered events we missed.
 *   - If the server emits ``resume.gap`` the client should clear local
 *     run state and refetch history via ``/api/qa/threads/{id}/messages``.
 *
 * The EventSource API is fine for our model (single-direction, server
 * → client, browser auto-reconnects with lastEventId). We override the
 * URL on each reconnect so the ``since_seq`` query param tracks our
 * cursor — that's a manual reconnect via ``onerror``, since EventSource
 * sends ``Last-Event-Id`` as a header but not a query param, and the
 * FastAPI route expects ``?since_seq`` for simplicity.
 */

// ── discriminated union: backend SSE events ─────────────────────────────────

export type QASSEEvent =
  | { event: "run.started"; data: { run_id: string; thread_id: string; started_at: number } }
  | { event: "text.delta"; data: { message_id: string | null; text: string } }
  | { event: "reasoning.delta"; data: { message_id: string | null; text: string } }
  | {
      event: "tool.call.started";
      data: {
        tool_call_id: string;
        name: string;
        args: Record<string, unknown>;
        started_at?: number;
      };
    }
  | {
      event: "tool.call.completed";
      data: {
        tool_call_id: string;
        result?: unknown;
        latency_ms?: number;
        error?: string;
      };
    }
  | {
      event: "audit.blocked";
      data: {
        tool_name: string;
        tool_args: Record<string, unknown>;
        blocked_reason: string;
        run_id?: string | null;
        thread_id?: string;
      };
    }
  | {
      event: "cost.updated";
      data: {
        input_tokens: number | null;
        output_tokens: number | null;
        model?: string | null;
      };
    }
  | {
      event: "ucm.final";
      data: {
        message_id: string | null;
        ucm: Record<string, unknown>;
        intent: string | null;
      };
    }
  | {
      event: "run.completed";
      data: {
        run_id: string;
        ended_at: number;
        status: "completed" | "cancelled" | "error";
        error?: string;
      };
    }
  | { event: "ping"; data: { ts: number } }
  | {
      event: "resume.gap";
      data: { reason: string; since_seq?: number; available_from?: number };
    }
  // The translator forwards unknown custom events under a namespaced
  // envelope — keep an escape hatch for forward compatibility.
  | {
      event: `custom.${string}`;
      data: Record<string, unknown>;
    };

export type QASSEHandlers = {
  /** Fired for every typed event from the wire. Default handler if no
   *  per-event handler matches. */
  onEvent?: (ev: QASSEEvent, seq: number) => void;
  /** Stream closed cleanly because the server sent ``run.completed``. */
  onClose?: (status: "completed" | "cancelled" | "error", error?: string) => void;
  /** Transport-level error (network drop, etc.). The client auto-
   *  reconnects unless ``abort()`` was called. */
  onError?: (err: Event) => void;
};

const EVENT_NAMES = new Set<string>([
  "run.started",
  "text.delta",
  "reasoning.delta",
  "tool.call.started",
  "tool.call.completed",
  "audit.blocked",
  "cost.updated",
  "ucm.final",
  "run.completed",
  "ping",
  "resume.gap",
]);

export type QAStreamConnection = {
  /** Close the underlying EventSource and stop reconnecting. */
  abort: () => void;
  /** Sequence number of the last event received from the server.
   *  Persisted across reconnects so resume works. */
  getLastSeq: () => number;
};

/**
 * Open an SSE connection against ``/api/qa/threads/{threadId}/stream``.
 *
 * The function returns immediately with an ``abort`` handle. Events
 * flow into ``handlers.onEvent`` asynchronously until either the
 * server closes the stream (``run.completed``) or ``abort()`` is
 * called.
 *
 * Reconnect semantics:
 *   - The browser's EventSource auto-reconnects on transport errors.
 *   - We re-construct the EventSource with a fresh URL (carrying
 *     ``since_seq=<lastSeq>``) when ``onerror`` fires AFTER a successful
 *     open — this lets the server replay events from its buffer.
 *   - We do NOT reconnect if the server emitted ``run.completed``.
 *   - We do NOT reconnect if the consumer called ``abort()``.
 */
export function openQAStream(
  threadId: string,
  runId: string,
  handlers: QASSEHandlers,
): QAStreamConnection {
  let aborted = false;
  let closed = false;
  let lastSeq = 0;
  let es: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const url = (): string => {
    const base = `/api/qa/threads/${threadId}/stream`;
    const params = new URLSearchParams({ run_id: runId });
    if (lastSeq > 0) params.set("since_seq", String(lastSeq));
    return `${base}?${params.toString()}`;
  };

  const handleMessage = (raw: MessageEvent<string>, eventName: string) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw.data);
    } catch {
      return;
    }
    // EventSource ``lastEventId`` carries the ``id:`` field. Empty
    // string for pings / resume.gap (we set seq=0 server-side for
    // those).
    const seq = raw.lastEventId ? Number(raw.lastEventId) || 0 : 0;
    if (seq > lastSeq) lastSeq = seq;

    if (!EVENT_NAMES.has(eventName) && !eventName.startsWith("custom.")) {
      return;
    }

    const ev = { event: eventName, data: parsed } as QASSEEvent;
    handlers.onEvent?.(ev, seq);

    if (ev.event === "run.completed") {
      closed = true;
      es?.close();
      es = null;
      handlers.onClose?.(ev.data.status, ev.data.error);
    }
  };

  const open = () => {
    if (aborted || closed) return;
    es = new EventSource(url(), { withCredentials: true });

    // Subscribe to each named event individually — EventSource only
    // dispatches to ``onmessage`` for unnamed (``event:`` absent)
    // payloads, and our server always names them.
    for (const name of EVENT_NAMES) {
      es.addEventListener(name, (ev) => handleMessage(ev as MessageEvent<string>, name));
    }
    // Generic listener for ``custom.*`` envelopes (forward-compat).
    es.addEventListener("message", (ev) =>
      handleMessage(ev as MessageEvent<string>, "message"),
    );

    es.onerror = (err) => {
      handlers.onError?.(err);
      if (aborted || closed) return;
      // The native EventSource will try to reconnect on its own with
      // the same URL. We let it for transient blips, but close and
      // reopen with a fresh ``since_seq`` after a short backoff so
      // the server-side replay buffer kicks in.
      es?.close();
      es = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(open, 1000);
    };
  };

  open();

  return {
    abort: () => {
      aborted = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      es?.close();
      es = null;
    },
    getLastSeq: () => lastSeq,
  };
}
