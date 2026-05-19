"use client";

/**
 * Thread pane — the central column of the Playground.
 *
 * Responsibilities:
 *   1. Show the message history for the active thread.
 *   2. Re-render each message through the channel selected in the
 *      header (web ⇄ whatsapp), reusing the canonical components
 *      from ``@nexus/ucm-render-web`` and ``@nexus/ucm-preview-whatsapp``.
 *   3. Provide a composer to send new messages.
 *
 * Phase 5 implementation: the live SSE conversation runtime
 * (``@assistant-ui/react-langgraph`` against the qa-langgraph-server)
 * is intentionally deferred to a follow-up — that integration was
 * validated end-to-end in the Fase 0 spike (``qa-spike/``) and just
 * needs to be lifted in once the server is up locally. For now we
 * render the persisted messages from ``qa-api`` and show a placeholder
 * for the composer; the empty-state guides the operator to create a
 * thread.
 */
import { useMemo } from "react";

import { UCMRenderer, type UCMMessage } from "@nexus/ucm-render-web";
import { WhatsAppPreview } from "@nexus/ucm-preview-whatsapp";

import type { QAThread } from "@/lib/qa-api";

import type { ChannelKind } from "./channel-selector";

export function ThreadPane({
  tenantId,
  channel,
  thread,
  onThreadCreated,
}: {
  tenantId: string;
  channel: ChannelKind;
  thread: QAThread | null;
  onThreadCreated: (t: QAThread) => void;
}) {
  // Phase-5 stub: no persisted UCM payloads on the thread row yet.
  // The qa-langgraph-server stream populates state["ucm"] (Fase 2
  // contract) per turn, so when the live runtime is mounted this
  // becomes a useState<UCMMessage[]> updated by the SSE event handler.
  const messages: UCMMessage[] = useMemo(() => [], [thread?.id]);

  if (thread == null) {
    return <EmptyState tenantId={tenantId} />;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-md rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            <strong className="block text-foreground">
              Conversación lista
            </strong>
            <p className="mt-1">
              El runtime live contra el LangGraph Server se conecta en
              una sesión separada. Mientras tanto, este panel es la
              persistencia (lo que <code>qa-api</code> sabe) para esta
              conversación.
            </p>
            <p className="mt-2 text-xs">
              thread <code className="font-mono">{thread.id}</code>
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-3">
            {messages.map((ucm) =>
              channel === "whatsapp" ? (
                <WhatsAppPreview key={ucm.message_id} ucm={ucm} />
              ) : (
                <UCMRenderer
                  key={ucm.message_id}
                  ucm={ucm}
                  onInteractive={(event) => {
                    // Placeholder — when the live runtime lands this
                    // calls the assistant-ui sendCommand / sendMessage
                    // with the interactive_response payload.
                    console.log("interactive_response", event);
                  }}
                />
              ),
            )}
          </div>
        )}
      </div>
      <ComposerStub
        disabled
        // The composer is wired live in the follow-up. We still render
        // it disabled so the operator sees the intended layout.
      />
    </div>
  );

  // unused-but-typed escape hatch so onThreadCreated keeps its
  // contract for the future live runtime (it triggers the parent
  // shell to register a new thread when the runtime auto-creates one).
  void onThreadCreated;
}

function EmptyState({ tenantId }: { tenantId: string }) {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md text-center text-sm text-muted-foreground">
        <strong className="block text-base text-foreground">
          Aún no abriste una conversación
        </strong>
        <p className="mt-2">
          Usá <kbd className="font-mono">+ nueva</kbd> en el panel izquierdo
          para crear un thread QA en este tenant ({" "}
          <code className="font-mono">{tenantId.slice(0, 8)}…</code> ). Todas
          las acciones quedan en sandbox <strong>dry-run</strong>.
        </p>
      </div>
    </div>
  );
}

function ComposerStub({ disabled }: { disabled?: boolean }) {
  return (
    <form
      onSubmit={(e) => e.preventDefault()}
      className="flex items-center gap-2 border-t border-border bg-card/40 p-3"
    >
      <input
        type="text"
        placeholder="Escribir mensaje… (runtime se conecta en una sesión separada)"
        disabled={disabled}
        className="flex-1 rounded border border-border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
      />
      <button
        type="submit"
        disabled={disabled}
        className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-[color:var(--color-on-primary,#fff)] disabled:cursor-not-allowed disabled:opacity-60"
      >
        Enviar
      </button>
    </form>
  );
}
