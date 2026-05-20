"use client";

/**
 * useQARuntime — assistant-ui adapter for the QA Playground (ADR-021 Fase 2).
 *
 * Wraps the streaming protocol defined in
 * ``apps/api/src/nexus_api/api/qa_streaming.py`` so it shows up as a
 * normal assistant-ui ``ExternalStoreRuntime``. The chat surface
 * (``<Thread>``, ``<Composer>``) sees a regular message list with
 * text + reasoning + tool-call + data parts, and the operator can
 * type / cancel / quick-reply without knowing about SSE.
 *
 * Lifecycle:
 *   1. Mount: hydrate the persisted history via
 *      ``GET /api/qa/threads/{id}/messages``.
 *   2. ``onNew``: POST ``/api/qa/threads/{id}/runs`` → get ``run_id``,
 *      open SSE against ``/api/qa/threads/{id}/stream``, accumulate
 *      events into the current assistant message.
 *   3. ``onCancel``: ``DELETE /api/qa/runs/{run_id}`` + abort the SSE.
 *
 * Notes on event → message-part mapping:
 *   - ``text.delta``        → grow the assistant message's text part.
 *   - ``reasoning.delta``   → grow a reasoning part.
 *   - ``tool.call.*``       → add / update a tool-call part keyed by
 *                             ``tool_call_id``.
 *   - ``ucm.final``         → push a ``data`` part with ``name: "ucm"``.
 *                             The thread-pane reads it to render the
 *                             UCM bubble via ``<UCMRenderer>`` /
 *                             ``<WhatsAppPreview>``.
 *   - ``audit.blocked``     → push a ``data`` part with ``name: "audit"``.
 *   - ``cost.updated``      → accumulate usage in message metadata.steps.
 *   - ``run.completed``     → flip ``status`` to complete / cancelled /
 *                             error and stop accepting events.
 */

import { useExternalStoreRuntime } from "@assistant-ui/react";
import type {
  AppendMessage,
  AssistantRuntime,
  DataMessagePart,
  MessageStatus,
  ReasoningMessagePart,
  TextMessagePart,
  ThreadAssistantMessage,
  ThreadAssistantMessagePart,
  ThreadMessage,
  ThreadUserMessage,
  ToolCallMessagePart,
} from "@assistant-ui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/** Minimal local type — assistant-ui doesn't re-export ``ThreadStep``
 *  but the shape is stable in ``ThreadAssistantMessage["metadata"].steps``. */
type LocalThreadStep = {
  readonly messageId?: string;
  readonly usage?: {
    readonly inputTokens: number;
    readonly outputTokens: number;
  };
};

function makeId(): string {
  // Browsers from 2022+ all expose ``crypto.randomUUID`` — keep this
  // dep-light instead of pulling nanoid which would add ~3KB.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `qa-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

import type { QAHistoryMessage } from "@/lib/qa-api";
import { openQAStream, type QAStreamConnection } from "@/lib/qa-sse";

// ── helpers: shape-correct empty message bodies ──────────────────────────────

const EMPTY_USER_METADATA: ThreadUserMessage["metadata"] = {
  custom: {},
};

const EMPTY_ASSISTANT_METADATA: ThreadAssistantMessage["metadata"] = {
  unstable_state: null,
  unstable_annotations: [],
  unstable_data: [],
  steps: [],
  custom: {},
};

function userMessage(text: string, id?: string): ThreadUserMessage {
  return {
    id: id ?? makeId(),
    role: "user",
    content: [{ type: "text", text }],
    attachments: [],
    createdAt: new Date(),
    metadata: EMPTY_USER_METADATA,
  };
}

function assistantMessage(
  parts: ThreadAssistantMessagePart[],
  status: MessageStatus,
  id?: string,
  metadata?: Partial<ThreadAssistantMessage["metadata"]>,
): ThreadAssistantMessage {
  return {
    id: id ?? makeId(),
    role: "assistant",
    content: parts,
    status,
    createdAt: new Date(),
    metadata: { ...EMPTY_ASSISTANT_METADATA, ...metadata },
  };
}

const RUNNING_STATUS: MessageStatus = { type: "running" };
const COMPLETE_STATUS: MessageStatus = { type: "complete", reason: "stop" };

// ── reducer: SSE event → next ThreadAssistantMessage ─────────────────────────
//
// The reducer is the pure surface of the runtime. It takes the
// current assistant message and one SSE event, returns the next
// assistant message. Easy to unit test.

type SSEEvent = Parameters<NonNullable<Parameters<typeof openQAStream>[2]["onEvent"]>>[0];

function appendOrCreateText(
  parts: readonly ThreadAssistantMessagePart[],
  text: string,
): ThreadAssistantMessagePart[] {
  const next = [...parts];
  for (let i = next.length - 1; i >= 0; i--) {
    const p = next[i];
    if (p.type === "text") {
      next[i] = { ...p, text: p.text + text } as TextMessagePart;
      return next;
    }
    // Stop scanning past non-text, non-reasoning parts — we don't
    // want to coalesce text across a tool-call boundary (Claude
    // emits text → tool → text and the UI must show them in order).
    if (p.type !== "reasoning") break;
  }
  next.push({ type: "text", text });
  return next;
}

function appendOrCreateReasoning(
  parts: readonly ThreadAssistantMessagePart[],
  text: string,
): ThreadAssistantMessagePart[] {
  const next = [...parts];
  for (let i = next.length - 1; i >= 0; i--) {
    const p = next[i];
    if (p.type === "reasoning") {
      next[i] = { ...p, text: p.text + text } as ReasoningMessagePart;
      return next;
    }
    if (p.type !== "text") break;
  }
  next.push({ type: "reasoning", text });
  return next;
}

function upsertToolCall(
  parts: readonly ThreadAssistantMessagePart[],
  toolCallId: string,
  patch: Partial<ToolCallMessagePart>,
  fallbackName?: string,
): ThreadAssistantMessagePart[] {
  const next = [...parts];
  for (let i = 0; i < next.length; i++) {
    const p = next[i];
    if (p.type === "tool-call" && p.toolCallId === toolCallId) {
      next[i] = { ...p, ...patch } as ToolCallMessagePart;
      return next;
    }
  }
  // First time we see this tool call.
  next.push({
    type: "tool-call",
    toolCallId,
    toolName: fallbackName ?? "unknown",
    args: {},
    argsText: "",
    ...patch,
  } as ToolCallMessagePart);
  return next;
}

function pushDataPart(
  parts: readonly ThreadAssistantMessagePart[],
  name: string,
  data: unknown,
): ThreadAssistantMessagePart[] {
  const part: DataMessagePart = { type: "data", name, data };
  return [...parts, part];
}

function applyEvent(
  msg: ThreadAssistantMessage,
  ev: SSEEvent,
): ThreadAssistantMessage {
  switch (ev.event) {
    case "text.delta": {
      if (!ev.data.text) return msg;
      return { ...msg, content: appendOrCreateText(msg.content, ev.data.text) };
    }
    case "reasoning.delta": {
      if (!ev.data.text) return msg;
      return {
        ...msg,
        content: appendOrCreateReasoning(msg.content, ev.data.text),
      };
    }
    case "tool.call.started": {
      return {
        ...msg,
        content: upsertToolCall(
          msg.content,
          ev.data.tool_call_id,
          {
            toolCallId: ev.data.tool_call_id,
            toolName: ev.data.name,
            // ``args`` is typed ``ReadonlyJSONObject`` on the
            // assistant-ui side. We trust the backend to send valid
            // JSON (it stringifies / parses through Pydantic), and
            // cast through unknown to satisfy the JSONObject narrowing.
            args: (ev.data.args ?? {}) as unknown as Parameters<typeof upsertToolCall>[2]["args"] & object,
            argsText: JSON.stringify(ev.data.args ?? {}),
          },
          ev.data.name,
        ),
      };
    }
    case "tool.call.completed": {
      return {
        ...msg,
        content: upsertToolCall(msg.content, ev.data.tool_call_id, {
          result: ev.data.result,
          isError: !!ev.data.error,
        }),
      };
    }
    case "ucm.final": {
      return { ...msg, content: pushDataPart(msg.content, "ucm", ev.data.ucm) };
    }
    case "audit.blocked": {
      return {
        ...msg,
        content: pushDataPart(msg.content, "audit", ev.data),
      };
    }
    case "cost.updated": {
      const step: LocalThreadStep = {
        usage: {
          inputTokens: ev.data.input_tokens ?? 0,
          outputTokens: ev.data.output_tokens ?? 0,
        },
      };
      return {
        ...msg,
        metadata: {
          ...msg.metadata,
          steps: [...msg.metadata.steps, step],
        },
      };
    }
    case "run.started":
    case "run.completed":
    case "ping":
    case "resume.gap":
    default:
      return msg;
  }
}

// ── history hydration ────────────────────────────────────────────────────────

function hydrateMessage(row: QAHistoryMessage): ThreadMessage {
  if (row.direction === "inbound") {
    return userMessage(row.content ?? "", row.id);
  }
  const parts: ThreadAssistantMessagePart[] = [];
  if (row.content) {
    parts.push({ type: "text", text: row.content });
  }
  if (row.ucm) {
    parts.push({ type: "data", name: "ucm", data: row.ucm });
  }
  return assistantMessage(parts, COMPLETE_STATUS, row.id);
}

// ── the hook ─────────────────────────────────────────────────────────────────

export type QARuntime = {
  runtime: AssistantRuntime;
  /** True while a streaming run is in flight on this thread. */
  isRunning: boolean;
  /** The current run id, or null when idle. Used by tests + the
   *  Inspector tabs to link to the Langfuse trace. */
  currentRunId: string | null;
  /** Forces a re-fetch of the persisted history (e.g. after a
   *  ``resume.gap`` SSE event told us the buffer is stale). */
  refreshHistory: () => void;
};

export function useQARuntime(threadId: string | null): QARuntime {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [historyTick, setHistoryTick] = useState(0);

  const connectionRef = useRef<QAStreamConnection | null>(null);
  // ID of the assistant message currently being grown by SSE events.
  // We mutate the messages array against this id so concurrent state
  // updates don't clobber prior parts.
  const activeAssistantIdRef = useRef<string | null>(null);

  // 1. Hydrate persisted history when the thread changes.
  useEffect(() => {
    if (!threadId) {
      setMessages([]);
      return;
    }
    const abort = new AbortController();
    fetch(`/api/qa/threads/${threadId}/messages?limit=100`, {
      signal: abort.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`messages ${r.status}`);
        return (await r.json()) as QAHistoryMessage[];
      })
      .then((rows) => {
        setMessages(rows.map(hydrateMessage));
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
        // Non-fatal: the operator can still send new turns; history
        // just stays empty until the next mount succeeds.
        console.warn("qa-runtime: history hydration failed", err);
      });
    return () => abort.abort();
  }, [threadId, historyTick]);

  // 2. Tear down any in-flight stream when the thread changes (or unmount).
  useEffect(() => {
    return () => {
      connectionRef.current?.abort();
      connectionRef.current = null;
      activeAssistantIdRef.current = null;
    };
  }, [threadId]);

  const updateAssistantMessage = useCallback(
    (id: string, mapper: (m: ThreadAssistantMessage) => ThreadAssistantMessage) => {
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== id || m.role !== "assistant") return m;
          return mapper(m as ThreadAssistantMessage);
        }),
      );
    },
    [],
  );

  const onNew = useCallback(
    async (message: AppendMessage) => {
      if (!threadId) throw new Error("qa-runtime: no active thread");
      // Extract the text the user typed. assistant-ui's AppendMessage
      // carries an array of message parts — we forward the first text
      // part. Attachments / images aren't supported yet (out of scope
      // for the Playground).
      const text = message.content
        .filter((p): p is TextMessagePart => p.type === "text")
        .map((p) => p.text)
        .join("");
      if (!text.trim()) return;

      // Optimistically add the user message.
      const userId = makeId();
      setMessages((prev) => [...prev, userMessage(text, userId)]);

      // Reserve an assistant message slot — events grow it as they arrive.
      const assistantId = makeId();
      activeAssistantIdRef.current = assistantId;
      setMessages((prev) => [
        ...prev,
        assistantMessage([], RUNNING_STATUS, assistantId),
      ]);
      setIsRunning(true);

      let runId: string;
      try {
        const r = await fetch(`/api/qa/threads/${threadId}/runs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        if (!r.ok) {
          const body = await r.text().catch(() => "");
          throw new Error(`runs POST ${r.status}: ${body.slice(0, 200)}`);
        }
        const out = (await r.json()) as { run_id: string };
        runId = out.run_id;
      } catch (err) {
        // Show the error in the assistant bubble; flip state back.
        updateAssistantMessage(assistantId, (m) => ({
          ...m,
          status: {
            type: "incomplete",
            reason: "error",
            error: String(err),
          },
        }));
        setIsRunning(false);
        activeAssistantIdRef.current = null;
        return;
      }
      setCurrentRunId(runId);

      // Open the SSE stream.
      connectionRef.current?.abort();
      connectionRef.current = openQAStream(threadId, runId, {
        onEvent: (ev) => {
          const target = activeAssistantIdRef.current;
          if (target == null) return;
          if (ev.event === "run.completed") {
            const finalStatus: MessageStatus =
              ev.data.status === "completed"
                ? { type: "complete", reason: "stop" }
                : ev.data.status === "cancelled"
                  ? {
                      type: "incomplete",
                      reason: "cancelled",
                    }
                  : {
                      type: "incomplete",
                      reason: "error",
                      error: ev.data.error,
                    };
            updateAssistantMessage(target, (m) => ({ ...m, status: finalStatus }));
            return;
          }
          if (ev.event === "resume.gap") {
            // Buffer overflowed mid-stream; the safest UX is to
            // refetch persisted history. Don't bin the active message
            // — the operator might still have useful partial output.
            setHistoryTick((n) => n + 1);
            return;
          }
          updateAssistantMessage(target, (m) => applyEvent(m, ev));
        },
        onClose: () => {
          setIsRunning(false);
          activeAssistantIdRef.current = null;
          connectionRef.current = null;
        },
        onError: () => {
          // Transport errors trigger the SSE client's auto-reconnect.
          // We don't flip isRunning so the composer stays disabled.
        },
      });
    },
    [threadId, updateAssistantMessage],
  );

  const onCancel = useCallback(async () => {
    const runId = currentRunId;
    connectionRef.current?.abort();
    connectionRef.current = null;
    if (!runId) {
      setIsRunning(false);
      activeAssistantIdRef.current = null;
      return;
    }
    try {
      await fetch(`/api/qa/runs/${runId}`, { method: "DELETE" });
    } catch (err) {
      console.warn("qa-runtime: cancel failed", err);
    }
    // ``run.completed`` should arrive via SSE shortly; but we already
    // aborted the connection, so flip the local state manually.
    const target = activeAssistantIdRef.current;
    if (target) {
      updateAssistantMessage(target, (m) => ({
        ...m,
        status: { type: "incomplete", reason: "cancelled" },
      }));
    }
    setIsRunning(false);
    activeAssistantIdRef.current = null;
  }, [currentRunId, updateAssistantMessage]);

  // assistant-ui expects ``setMessages: (m: readonly ThreadMessage[]) => void``;
  // React's setState is wider (also accepts updater fns) — adapt via a
  // bound wrapper instead of casting away the readonly contract.
  const setMessagesAdapter = useCallback(
    (m: readonly ThreadMessage[]) => setMessages([...m]),
    [],
  );

  const runtime = useExternalStoreRuntime({
    messages,
    setMessages: setMessagesAdapter,
    isRunning,
    onNew,
    onCancel,
  });

  const refreshHistory = useCallback(() => setHistoryTick((n) => n + 1), []);

  return useMemo(
    () => ({ runtime, isRunning, currentRunId, refreshHistory }),
    [runtime, isRunning, currentRunId, refreshHistory],
  );
}

// ── exports for tests ───────────────────────────────────────────────────────

export const __testing = {
  applyEvent,
  hydrateMessage,
  appendOrCreateText,
  appendOrCreateReasoning,
  upsertToolCall,
  assistantMessage,
  userMessage,
};
