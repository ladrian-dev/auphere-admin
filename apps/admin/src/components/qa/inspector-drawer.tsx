"use client";

/**
 * Inspector drawer — right rail of the Playground.
 *
 * 5 tabs (per ADR-020 / feature spec):
 *   Tools     — what tool calls happened this turn (name, args, result, latency)
 *   Reasoning — chain-of-thought blocks emitted by the LLM
 *   Trace     — link to the Langfuse trace for this run
 *   Cost      — token + USD cost for the turn
 *   Audit     — dry-run side-effects intercepted in this thread
 *
 * Phase 5 implementation: Audit is fully live (it queries the
 * persistent qa-api). The other four tabs are structural placeholders
 * with the layout already in place — they get populated when the live
 * assistant-ui runtime feeds per-turn telemetry into the shell.
 */
import { useEffect, useState } from "react";

import type { QASideEffectAudit, QAThread } from "@/lib/qa-api";

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
}: {
  tenantId: string;
  thread: QAThread | null;
}) {
  const [active, setActive] = useState<TabKey>("audit");

  return (
    <aside
      aria-label="QA inspector"
      className="flex min-h-0 flex-col bg-card/40"
    >
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
          <AuditTab thread={thread} />
        ) : active === "tools" ? (
          <Placeholder
            title="Tools"
            description="Cada tool call del turno actual (name, args, result, latencia). Se llena cuando el runtime live emite eventos por turno."
          />
        ) : active === "reasoning" ? (
          <Placeholder
            title="Reasoning"
            description="Bloques de chain-of-thought de Claude 4.6, colapsables. Llega cuando el runtime live procesa thinking blocks."
          />
        ) : active === "trace" ? (
          <Placeholder
            title="Trace"
            description="Link al trace en Langfuse para el run en curso. Llega cuando el runtime expone el run_id."
            footnote={`tenant=${tenantId.slice(0, 8)}…`}
          />
        ) : (
          <Placeholder
            title="Cost"
            description="Tokens in/out + costo USD del turno. Llega cuando el runtime expone usage_metadata."
          />
        )}
      </div>
    </aside>
  );
}

function AuditTab({ thread }: { thread: QAThread | null }) {
  const [rows, setRows] = useState<QASideEffectAudit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!thread) {
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
  }, [thread?.id]);

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

function Placeholder({
  title,
  description,
  footnote,
}: {
  title: string;
  description: string;
  footnote?: string;
}) {
  return (
    <div className="rounded border border-dashed border-border p-3 text-xs text-muted-foreground">
      <strong className="block text-foreground">{title}</strong>
      <p className="mt-1 leading-snug">{description}</p>
      {footnote && (
        <span className="mt-2 block font-mono text-[10px]">{footnote}</span>
      )}
    </div>
  );
}
