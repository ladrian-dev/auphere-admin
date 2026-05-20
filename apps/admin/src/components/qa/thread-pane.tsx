"use client";

/**
 * Thread pane — central column of the Playground (ADR-020 Fase 5 closure).
 *
 * Responsibilities:
 *   1. Show the message history for the active thread.
 *   2. Re-render each message through the channel selected in the
 *      header (web ⇄ whatsapp), reusing the canonical components from
 *      ``@nexus/ucm-render-web`` and ``@nexus/ucm-preview-whatsapp``.
 *   3. Composer enabled — POSTs the message to ``/api/qa/threads/{id}/send``
 *      which orchestrates: auto-seed customer/conv → inbound row →
 *      qa-langgraph-server run → returns final UCM.
 *
 * The composer is synchronous from the operator's POV: one POST in,
 * one UCM back. Visible token streaming lands when assistant-ui is
 * wired in a follow-up session — this stub is enough for the 9/9
 * human acceptance because every turn cleanly renders the agent's
 * final UCM.
 */
import { FormEvent, useCallback, useMemo, useRef, useState } from "react";

import {
  UCMRenderer,
  type InteractiveResponse,
  type UCMMessage,
} from "@nexus/ucm-render-web";
import { WhatsAppPreview } from "@nexus/ucm-preview-whatsapp";

import type { QAThread } from "@/lib/qa-api";

import type { ChannelKind } from "./channel-selector";

type Turn =
  | { kind: "user"; text: string; ts: number }
  | { kind: "agent"; ucm: UCMMessage; intent: string | null; ts: number }
  | { kind: "error"; detail: string; ts: number };

export function ThreadPane({
  tenantId,
  channel,
  thread,
  onThreadCreated,
  onTurnComplete,
}: {
  tenantId: string;
  channel: ChannelKind;
  thread: QAThread | null;
  onThreadCreated: (t: QAThread) => void;
  /** Bumped after each successful turn so the inspector refetches audit. */
  onTurnComplete?: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [composer, setComposer] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset the local history when the operator switches threads.
  useMemo(() => {
    setTurns([]);
    setComposer("");
  }, [thread?.id]);

  const onSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!thread) return;
      const text = composer.trim();
      if (!text || busy) return;
      setBusy(true);
      const userTurn: Turn = { kind: "user", text, ts: Date.now() };
      setTurns((prev) => [...prev, userTurn]);
      setComposer("");
      try {
        const res = await fetch(`/api/qa/threads/${thread.id}/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        if (!res.ok) {
          const body = await res.text().catch(() => "");
          throw new Error(
            `HTTP ${res.status}: ${body.slice(0, 200) || "no body"}`,
          );
        }
        const data = (await res.json()) as {
          response: string;
          ucm: unknown;
          intent: string | null;
          tool_calls: unknown[];
        };
        if (!data.ucm) {
          throw new Error("backend returned no UCM payload");
        }
        setTurns((prev) => [
          ...prev,
          {
            kind: "agent",
            ucm: data.ucm as UCMMessage,
            intent: data.intent ?? null,
            ts: Date.now(),
          },
        ]);
        onTurnComplete?.();
      } catch (err) {
        setTurns((prev) => [
          ...prev,
          {
            kind: "error",
            detail: err instanceof Error ? err.message : String(err),
            ts: Date.now(),
          },
        ]);
      } finally {
        setBusy(false);
        // Restore focus so the operator can keep typing without clicking.
        inputRef.current?.focus();
      }
    },
    [composer, busy, thread, onTurnComplete],
  );

  if (thread == null) {
    return <EmptyState tenantId={tenantId} />;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {turns.length === 0 ? (
          <div className="mx-auto max-w-md rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            <strong className="block text-foreground">
              Conversación lista
            </strong>
            <p className="mt-1">
              Escribí un mensaje abajo para arrancar el turno. Todo
              ocurre en sandbox <strong>dry-run</strong>: nada de lo
              que el agente intente hacer (reservas, mensajes salientes,
              llamadas externas) toca el mundo real.
            </p>
            <p className="mt-2 text-xs">
              thread <code className="font-mono">{thread.id}</code>
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-3">
            {turns.map((t) =>
              t.kind === "user" ? (
                <UserBubble key={t.ts} text={t.text} />
              ) : t.kind === "agent" ? (
                channel === "whatsapp" ? (
                  <WhatsAppPreview key={t.ts} ucm={t.ucm} />
                ) : (
                  <UCMRenderer
                    key={t.ts}
                    ucm={t.ucm}
                    onInteractive={(event: InteractiveResponse) => {
                      // Quick replies / lists send back an
                      // interactive_response payload. Until the
                      // streaming runtime is wired, log it — the
                      // operator can see the click landed.
                      console.log("interactive_response", event);
                    }}
                  />
                )
              ) : (
                <ErrorBubble key={t.ts} detail={t.detail} />
              ),
            )}
            {busy && <PendingBubble />}
          </div>
        )}
      </div>
      <form
        onSubmit={onSubmit}
        className="flex items-center gap-2 border-t border-border bg-card/40 p-3"
      >
        <input
          ref={inputRef}
          type="text"
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          placeholder="Escribí como si fueras el cliente final…"
          disabled={busy}
          className="flex-1 rounded border border-border bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
          autoFocus
        />
        <button
          type="submit"
          disabled={busy || !composer.trim()}
          className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-[color:var(--color-on-primary,#fff)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Enviando…" : "Enviar"}
        </button>
      </form>
      <ChannelHintFooter channel={channel} />
    </div>
  );

  // Unused-but-typed escape hatch so onThreadCreated keeps its contract
  // for when the streaming runtime mounts and may auto-create threads.
  void onThreadCreated;
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="self-end max-w-[80%] rounded-2xl rounded-br-sm bg-[color:var(--color-primary)] px-4 py-2 text-sm text-[color:var(--color-on-primary,#fff)]">
      {text}
    </div>
  );
}

function PendingBubble() {
  return (
    <div className="self-start max-w-[80%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2 text-sm text-muted-foreground italic">
      El agente está pensando…
    </div>
  );
}

function ErrorBubble({ detail }: { detail: string }) {
  return (
    <div className="self-start max-w-[90%] rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
      <strong>Error en el turno:</strong> {detail}
    </div>
  );
}

function ChannelHintFooter({ channel }: { channel: ChannelKind }) {
  return (
    <div className="border-t border-border bg-card/20 px-3 py-1.5 text-[10px] text-muted-foreground">
      Preview activo: <strong className="uppercase">{channel}</strong>. La
      respuesta del agente se re-renderiza al cambiar el canal — sin
      re-ejecutar el turno.
    </div>
  );
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
