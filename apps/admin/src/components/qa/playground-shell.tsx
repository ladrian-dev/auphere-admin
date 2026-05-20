"use client";

/**
 * QA Playground shell — 3-column layout (ADR-020 Phase 5).
 *
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │ header: tenant · agent vX · DRY RUN badge                        │
 *   ├──────────┬────────────────────────────────────────┬──────────────┤
 *   │          │                                        │              │
 *   │ Threads  │  Thread (PreviewChannelSelector +      │  Inspector   │
 *   │          │   messages + composer)                 │  (5 tabs)    │
 *   │          │                                        │              │
 *   └──────────┴────────────────────────────────────────┴──────────────┘
 *
 * The shell keeps minimal state: which thread is active and which
 * channel is selected for preview. Everything else (messages, audit,
 * tool calls) is owned by sub-components that fetch / stream their
 * own data scoped to the active thread.
 *
 * The runtime that drives the conversation is mounted inside
 * ``<ThreadPane>`` — see ``./thread-pane.tsx``. In Phase 5 it stays
 * as a stub that renders persisted messages from qa-api; the live
 * SSE connection to ``apps/qa-langgraph-server`` lands when that
 * service is wired into local dev (already validated in the Fase 0
 * spike).
 */
import { useCallback, useMemo, useState, useTransition } from "react";
// `auditRefreshKey` bumps after each successful turn so the inspector's
// Audit tab re-fetches and shows freshly-blocked side-effects without
// the operator having to switch tabs.
import { useRouter } from "next/navigation";

import type { QAThread } from "@/lib/qa-api";
import type { QARuntime } from "@/lib/qa-runtime";

import { ChannelKindSelector, type ChannelKind } from "./channel-selector";
import { InspectorDrawer } from "./inspector-drawer";
import { ThreadList } from "./thread-list";
import { ThreadPane } from "./thread-pane";

export function PlaygroundShell({
  tenant,
  agentVersion,
  operatorId,
  operatorEmail,
  initialThreads,
  initialActiveThread,
}: {
  tenant: { id: string; name: string; slug: string };
  agentVersion: number | null;
  operatorId: string;
  operatorEmail: string | null;
  initialThreads: QAThread[];
  initialActiveThread: QAThread | null;
}) {
  const router = useRouter();
  const [threads, setThreads] = useState<QAThread[]>(initialThreads);
  const [activeThread, setActiveThread] = useState<QAThread | null>(
    initialActiveThread,
  );
  const [channel, setChannel] = useState<ChannelKind>("web");
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [auditRefreshKey, setAuditRefreshKey] = useState(0);
  const [qaRuntime, setQARuntime] = useState<QARuntime | null>(null);
  const [, startTransition] = useTransition();

  const selectThread = useCallback(
    (thread: QAThread | null) => {
      setActiveThread(thread);
      const search = thread ? `?thread=${thread.id}` : "";
      startTransition(() => {
        router.replace(`/qa/${tenant.id}/chat${search}`, { scroll: false });
      });
    },
    [router, tenant.id],
  );

  const onCreateThread = useCallback(
    async (title?: string) => {
      const res = await fetch(`/api/qa/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenant.id, title }),
      });
      if (!res.ok) {
        throw new Error(`createThread failed (${res.status})`);
      }
      const thread = (await res.json()) as QAThread;
      setThreads((prev) => [thread, ...prev]);
      selectThread(thread);
    },
    [selectThread, tenant.id],
  );

  const onAddOptimisticThread = useCallback((thread: QAThread) => {
    setThreads((prev) =>
      prev.some((t) => t.id === thread.id) ? prev : [thread, ...prev],
    );
  }, []);

  const headerSummary = useMemo(
    () => ({
      tenantLabel: `${tenant.name}`,
      tenantSlug: tenant.slug,
      agentLabel:
        agentVersion != null ? `Agente v${agentVersion}` : "Agente (sin versión)",
    }),
    [agentVersion, tenant.name, tenant.slug],
  );

  return (
    <div
      className="grid h-[calc(100vh-3rem)] w-full grid-rows-[auto_minmax(0,1fr)] bg-background"
      data-qa-playground-root
    >
      {/* Header */}
      <header className="flex items-center gap-4 border-b border-border bg-card/50 px-4 py-2.5 text-sm">
        <div className="flex flex-col">
          <span className="font-semibold tracking-tight">
            {headerSummary.tenantLabel}
          </span>
          <span className="font-mono text-xs text-muted-foreground">
            {headerSummary.tenantSlug} · {headerSummary.agentLabel}
          </span>
        </div>
        <span
          aria-label="Dry run sandbox"
          className="ml-2 rounded-full bg-[#ffe082] px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-[#7a4f00]"
        >
          Dry run
        </span>
        <div className="flex-1" />
        {operatorEmail && (
          <span
            className="text-xs text-muted-foreground"
            title={`operator_id=${operatorId}`}
          >
            {operatorEmail}
          </span>
        )}
        <button
          type="button"
          onClick={() => setInspectorOpen((v) => !v)}
          className="rounded border border-border px-2 py-1 text-xs hover:bg-muted"
          aria-pressed={inspectorOpen}
        >
          {inspectorOpen ? "Cerrar inspector" : "Abrir inspector"}
        </button>
      </header>

      {/* Body */}
      <div
        className={`grid min-h-0 ${
          inspectorOpen
            ? "grid-cols-[260px_minmax(0,1fr)_360px]"
            : "grid-cols-[260px_minmax(0,1fr)]"
        }`}
      >
        <ThreadList
          threads={threads}
          activeThreadId={activeThread?.id ?? null}
          onSelect={selectThread}
          onCreate={onCreateThread}
        />
        <main className="flex min-h-0 flex-col border-x border-border">
          <div className="flex items-center justify-between border-b border-border bg-muted/30 px-4 py-2">
            <ChannelKindSelector value={channel} onChange={setChannel} />
            <span className="font-mono text-[11px] text-muted-foreground">
              {activeThread ? `thread=${activeThread.id.slice(0, 8)}…` : "no thread"}
            </span>
          </div>
          <ThreadPane
            tenantId={tenant.id}
            channel={channel}
            thread={activeThread}
            onThreadCreated={(t) => {
              onAddOptimisticThread(t);
              selectThread(t);
            }}
            onTurnComplete={() => setAuditRefreshKey((n) => n + 1)}
            onRuntimeReady={setQARuntime}
          />
        </main>
        {inspectorOpen && (
          <InspectorDrawer
            tenantId={tenant.id}
            thread={activeThread}
            refreshKey={auditRefreshKey}
            qaRuntime={qaRuntime}
          />
        )}
      </div>
    </div>
  );
}
