"use client";

/**
 * Inspector drawer — right rail of the Playground (ADR-021 Fase 2).
 *
 * 5 tabs, all live now:
 *   Tools     — tool calls of the current run, pulled from the assistant
 *               message's ``tool-call`` parts as SSE events arrive.
 *   Reasoning — chain-of-thought blocks (``reasoning`` parts).
 *   Trace     — link to Langfuse for the current run id.
 *   Cost      — token totals aggregated from ``cost.updated`` SSE events
 *               (sum of all LLM calls in the turn).
 *   Audit     — dry-run side-effects from ``qa.side_effect_audit``,
 *               refreshed when ``refreshKey`` bumps.
 */
import { useEffect, useMemo, useState } from "react";

import type { ThreadAssistantMessage, ThreadMessage } from "@assistant-ui/react";

import type { QASideEffectAudit, QAThread } from "@/lib/qa-api";
import type { QARuntime } from "@/lib/qa-runtime";

const TABS = [
  { key: "tools", label: "Tools" },
  { key: "reasoning", label: "Reasoning" },
  { key: "trace", label: "Trace" },
  { key: "cost", label: "Cost" },
  { key: "audit", label: "Audit" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function InspectorDrawer({
  tenantId,
  thread,
  refreshKey,
  qaRuntime,
}: {
  tenantId: string;
  thread: QAThread | null;
  /** Bumped by the shell after each turn so the Audit tab re-fetches
   *  without polling. */
  refreshKey?: number;
  /** Provided once the ThreadPane mounts. Lets the live tabs read the
   *  current assistant message's parts and totals. */
  qaRuntime?: QARuntime | null;
}) {
  const [active, setActive] = useState<TabKey>("audit");
  const lastAssistant = useLastAssistantMessage(qaRuntime ?? null);

  return (
    <aside aria-label="QA inspector" className="flex min-h-0 flex-col bg-card/40">
      <div
        role="tablist"
        className="flex items-stretch gap-1 border-b border-border px-2 py-2"
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active === tab.key}
            onClick={() => setActive(tab.key)}
            className={`rounded px-2 py-1 text-xs ${
              active === tab.key
                ? "bg-muted font-medium"
                : "hover:bg-muted/60 text-muted-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {active === "audit" ? (
          <AuditTab thread={thread} refreshKey={refreshKey} />
        ) : active === "tools" ? (
          <ToolsTab message={lastAssistant} />
        ) : active === "reasoning" ? (
          <ReasoningTab message={lastAssistant} />
        ) : active === "trace" ? (
          <TraceTab tenantId={tenantId} runId={qaRuntime?.currentRunId ?? null} />
        ) : (
          <CostTab message={lastAssistant} />
        )}
      </div>
    </aside>
  );
}

// ── runtime → assistant message subscription ─────────────────────────────────

function useLastAssistantMessage(
  qaRuntime: QARuntime | null,
): ThreadAssistantMessage | null {
  const [messages, setMessages] = useState<readonly ThreadMessage[]>(
    qaRuntime?.runtime.thread.getState().messages ?? [],
  );
  // The setMessages([]) reset when qaRuntime disappears is the
  // documented pattern for "clear stale data when prop unmounts".
  // React 19's react-hooks/set-state-in-effect flags it; the
  // alternative (key-based remount) would re-render this whole tab
  // for every thread switch. Disabled inline, same justification as
  // AuditTab below.
  useEffect(() => {
    if (!qaRuntime) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([]);
      return;
    }
    setMessages(qaRuntime.runtime.thread.getState().messages);
    const unsub = qaRuntime.runtime.thread.subscribe(() => {
      setMessages(qaRuntime.runtime.thread.getState().messages);
    });
    return () => unsub();
  }, [qaRuntime]);

  return useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant") return m as ThreadAssistantMessage;
    }
    return null;
  }, [messages]);
}

// ── live tabs ───────────────────────────────────────────────────────────────

function ToolsTab({ message }: { message: ThreadAssistantMessage | null }) {
  const calls = useMemo(
    () =>
      (message?.content ?? []).filter(
        (p): p is Extract<ThreadAssistantMessage["content"][number], { type: "tool-call" }> =>
          p.type === "tool-call",
      ),
    [message],
  );
  if (!message) {
    return (
      <p className="text-xs text-muted-foreground">
        Aún no se ha ejecutado ningún turno en este thread.
      </p>
    );
  }
  if (calls.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        El agente no llamó ninguna tool en este turno.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {calls.map((c, i) => (
        <li
          key={`${c.toolCallId}-${i}`}
          className="rounded border border-border bg-background p-2 text-xs"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono font-medium">{c.toolName}</span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                c.result !== undefined
                  ? c.isError
                    ? "bg-red-100 text-red-800"
                    : "bg-green-100 text-green-800"
                  : "bg-yellow-100 text-yellow-800"
              }`}
            >
              {c.result !== undefined ? (c.isError ? "error" : "done") : "running"}
            </span>
          </div>
          {c.argsText && (
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-[11px] text-muted-foreground">
              {c.argsText}
            </pre>
          )}
          {c.result !== undefined && (
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-[11px] text-muted-foreground">
              {typeof c.result === "string"
                ? c.result
                : JSON.stringify(c.result, null, 2)}
            </pre>
          )}
        </li>
      ))}
    </ul>
  );
}

function ReasoningTab({ message }: { message: ThreadAssistantMessage | null }) {
  const reasoning = useMemo(
    () =>
      (message?.content ?? []).filter(
        (p): p is Extract<ThreadAssistantMessage["content"][number], { type: "reasoning" }> =>
          p.type === "reasoning",
      ),
    [message],
  );
  if (!message) {
    return (
      <p className="text-xs text-muted-foreground">
        Aún no se ha ejecutado ningún turno en este thread.
      </p>
    );
  }
  if (reasoning.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        El modelo no emitió bloques de razonamiento en este turno
        (típico de modelos no Claude 4.6 / o1).
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {reasoning.map((r, i) => (
        <details
          key={i}
          className="rounded border border-border bg-background p-2 text-xs"
          open
        >
          <summary className="cursor-pointer select-none text-[11px] uppercase tracking-wide text-muted-foreground">
            Bloque {i + 1}
          </summary>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px]">
            {r.text}
          </pre>
        </details>
      ))}
    </div>
  );
}

function CostTab({ message }: { message: ThreadAssistantMessage | null }) {
  const totals = useMemo(() => {
    let inTok = 0;
    let outTok = 0;
    for (const step of message?.metadata.steps ?? []) {
      inTok += step.usage?.inputTokens ?? 0;
      outTok += step.usage?.outputTokens ?? 0;
    }
    return { inTok, outTok };
  }, [message]);
  if (!message) {
    return (
      <p className="text-xs text-muted-foreground">
        Aún no se ha ejecutado ningún turno en este thread.
      </p>
    );
  }
  if (totals.inTok === 0 && totals.outTok === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        El runtime aún no reportó tokens (esperá a que el LLM cierre el
        primer ``on_chat_model_end``).
      </p>
    );
  }
  return (
    <dl className="grid grid-cols-2 gap-2 text-xs">
      <dt className="text-muted-foreground">Input tokens</dt>
      <dd className="font-mono">{totals.inTok}</dd>
      <dt className="text-muted-foreground">Output tokens</dt>
      <dd className="font-mono">{totals.outTok}</dd>
      <dt className="text-muted-foreground">Steps (LLM calls)</dt>
      <dd className="font-mono">{message.metadata.steps?.length ?? 0}</dd>
    </dl>
  );
}

function TraceTab({
  tenantId,
  runId,
}: {
  tenantId: string;
  runId: string | null;
}) {
  return (
    <div className="rounded border border-dashed border-border p-3 text-xs text-muted-foreground">
      <strong className="block text-foreground">Trace</strong>
      <p className="mt-1 leading-snug">
        Link al trace en Langfuse para el run en curso. El trace_id sale
        en la metadata del run cuando el SDK de Langfuse esté wireado al
        runtime.
      </p>
      <div className="mt-2 flex flex-col gap-1 font-mono text-[10px]">
        <span>tenant={tenantId.slice(0, 8)}…</span>
        <span>run={runId ? runId.slice(0, 8) + "…" : "idle"}</span>
      </div>
    </div>
  );
}

// ── audit tab (unchanged from Fase 5) ───────────────────────────────────────

function AuditTab({
  thread,
  refreshKey,
}: {
  thread: QAThread | null;
  refreshKey?: number;
}) {
  const [rows, setRows] = useState<QASideEffectAudit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The ``setRows([])`` reset for the ``no thread`` branch is the
  // documented pattern for "clear stale data when prop disappears".
  // React 19's ``react-hooks/set-state-in-effect`` flags it, but the
  // alternative (deriving from props) doesn't fit the async fetch
  // path that follows.
  useEffect(() => {
    if (!thread) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setRows([]);
      return;
    }
    const abort = new AbortController();
    setRows(null);
    setError(null);
    fetch(`/api/qa/threads/${thread.id}/audit`, { signal: abort.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`audit ${res.status}`);
        return res.json() as Promise<QASideEffectAudit[]>;
      })
      .then((data) => setRows(data))
      .catch((err) => {
        if (err.name === "AbortError") return;
        setError(String(err));
      });
    return () => abort.abort();
  }, [thread?.id, refreshKey]);

  if (!thread) {
    return (
      <p className="text-xs text-muted-foreground">
        Seleccioná o creá una conversación para ver su audit.
      </p>
    );
  }
  if (error) {
    return (
      <p className="text-xs text-[color:var(--color-danger,#c0392b)]">
        Error cargando audit: {error}
      </p>
    );
  }
  if (rows == null) {
    return <p className="text-xs text-muted-foreground">Cargando…</p>;
  }
  if (rows.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Sin side-effects interceptados en este thread todavía. Cualquier
        tool call con side_effects no vacío se persiste acá.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r) => (
        <li
          key={r.id}
          className="rounded border border-border bg-background p-2 text-xs"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono font-medium">{r.tool_name}</span>
            <span className="rounded bg-[#ffe082] px-1.5 py-0.5 text-[10px] font-bold uppercase text-[#7a4f00]">
              {r.blocked_reason}
            </span>
          </div>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-[11px] text-muted-foreground">
            {JSON.stringify(r.tool_args, null, 2)}
          </pre>
          <span className="font-mono text-[10px] text-muted-foreground">
            {new Date(r.created_at).toLocaleString()}
            {r.run_id ? ` · run=${r.run_id}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
