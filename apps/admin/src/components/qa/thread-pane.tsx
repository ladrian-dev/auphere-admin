"use client";

/**
 * Thread pane — central column of the Playground (ADR-021 Fase 2).
 *
 * Mounted under the assistant-ui ``AssistantRuntimeProvider`` so the
 * composer / message list are driven by the SSE-backed runtime in
 * ``@/lib/qa-runtime``. Each agent turn streams ``text.delta`` /
 * ``reasoning.delta`` / ``tool.call.*`` / ``ucm.final`` events; the
 * runtime mutates the messages array and we render manually.
 *
 * We don't use ``ThreadPrimitive`` for the message list — assistant-ui's
 * primitives are great for the chat UX but the Playground needs a
 * channel-aware UCM renderer in the middle of the assistant message,
 * which is simpler to express by iterating ``thread.messages`` directly
 * than by hooking the primitive's render slots. The composer still uses
 * standard inputs — we get streaming visibility, stop button, and quick-
 * reply round-trip without depending on more of the primitive API than
 * necessary.
 */
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import type {
  ThreadAssistantMessage,
  ThreadAssistantMessagePart,
  ThreadMessage,
  ThreadUserMessage,
} from "@assistant-ui/react";
import { WhatsAppPreview } from "@nexus/ucm-preview-whatsapp";
import {
  UCMRenderer,
  type InteractiveResponse,
  type UCMMessage,
} from "@nexus/ucm-render-web";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type { QAThread } from "@/lib/qa-api";
import { useQARuntime, type QARuntime } from "@/lib/qa-runtime";

import type { ChannelKind } from "./channel-selector";

export function ThreadPane({
  tenantId,
  channel,
  thread,
  onThreadCreated,
  onTurnComplete,
  onRuntimeReady,
}: {
  tenantId: string;
  channel: ChannelKind;
  thread: QAThread | null;
  onThreadCreated: (t: QAThread) => void;
  /** Bumped after each successful turn so the inspector refetches audit. */
  onTurnComplete?: () => void;
  /** Called once per render with the current runtime object so the
   *  parent shell can hand it to the inspector tabs. */
  onRuntimeReady?: (qaRuntime: QARuntime) => void;
}) {
  const qaRuntime = useQARuntime(thread?.id ?? null);
  const wasRunningRef = useRef(false);

  // Expose runtime up to the shell so the inspector tabs subscribe.
  useEffect(() => {
    onRuntimeReady?.(qaRuntime);
  }, [qaRuntime, onRuntimeReady]);

  // Fire ``onTurnComplete`` when a streaming turn transitions from
  // running → done so the Audit tab re-fetches without polling.
  useEffect(() => {
    if (wasRunningRef.current && !qaRuntime.isRunning) {
      onTurnComplete?.();
    }
    wasRunningRef.current = qaRuntime.isRunning;
  }, [qaRuntime.isRunning, onTurnComplete]);

  if (thread == null) {
    return <EmptyState tenantId={tenantId} />;
  }

  return (
    <AssistantRuntimeProvider runtime={qaRuntime.runtime}>
      <ThreadView
        thread={thread}
        channel={channel}
        qaRuntime={qaRuntime}
      />
      {/* unused-but-typed escape hatch; the auto-create flow lives in PlaygroundShell */}
      {void onThreadCreated}
    </AssistantRuntimeProvider>
  );
}

function ThreadView({
  thread,
  channel,
  qaRuntime,
}: {
  thread: QAThread;
  channel: ChannelKind;
  qaRuntime: QARuntime;
}) {
  // The runtime owns the messages — we read them via the runtime's
  // current snapshot rather than threading them through props.
  // ``runtime.thread.getState().messages`` is the assistant-ui public
  // accessor; we subscribe to the same state via a poll-free
  // subscription pattern below.
  const [messages, setMessages] = useState<readonly ThreadMessage[]>(
    qaRuntime.runtime.thread.getState().messages,
  );
  useEffect(() => {
    const unsub = qaRuntime.runtime.thread.subscribe(() => {
      setMessages(qaRuntime.runtime.thread.getState().messages);
    });
    return () => unsub();
  }, [qaRuntime.runtime]);

  const [composer, setComposer] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = qaRuntime.isRunning;

  const onSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const text = composer.trim();
      if (!text || busy) return;
      setComposer("");
      try {
        await qaRuntime.runtime.thread.append({
          role: "user",
          content: [{ type: "text", text }],
        });
      } catch (err) {
        console.warn("thread-pane: append failed", err);
      } finally {
        inputRef.current?.focus();
      }
    },
    [busy, composer, qaRuntime.runtime],
  );

  const onCancel = useCallback(() => {
    qaRuntime.runtime.thread.cancelRun();
  }, [qaRuntime.runtime]);

  // Quick-reply / list-row click → send the canonical ``id`` back as a
  // user turn. The agent expects the id, not the title; UCM render
  // components pass both in the event payload.
  const onInteractive = useCallback(
    async (event: InteractiveResponse) => {
      if (busy) return;
      try {
        await qaRuntime.runtime.thread.append({
          role: "user",
          content: [{ type: "text", text: event.id }],
        });
      } catch (err) {
        console.warn("thread-pane: interactive append failed", err);
      }
    },
    [busy, qaRuntime.runtime],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 ? (
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
            {messages.map((msg) =>
              msg.role === "user" ? (
                <UserBubble key={msg.id} message={msg} />
              ) : msg.role === "assistant" ? (
                <AssistantBubble
                  key={msg.id}
                  message={msg}
                  channel={channel}
                  onInteractive={onInteractive}
                />
              ) : null,
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
        {busy ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-border bg-card px-3 py-2 text-sm font-medium hover:bg-muted"
          >
            Detener
          </button>
        ) : (
          <button
            type="submit"
            disabled={!composer.trim()}
            className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-[color:var(--color-on-primary,#fff)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            Enviar
          </button>
        )}
      </form>
      <ChannelHintFooter channel={channel} />
    </div>
  );
}

// ── message renderers ────────────────────────────────────────────────────────

function UserBubble({ message }: { message: ThreadUserMessage }) {
  const text = message.content
    .filter((p) => p.type === "text")
    .map((p) => (p as { text: string }).text)
    .join("");
  return (
    <div className="self-end max-w-[80%] rounded-2xl rounded-br-sm bg-[color:var(--color-primary)] px-4 py-2 text-sm text-[color:var(--color-on-primary,#fff)]">
      {text}
    </div>
  );
}

function AssistantBubble({
  message,
  channel,
  onInteractive,
}: {
  message: ThreadAssistantMessage;
  channel: ChannelKind;
  onInteractive: (event: InteractiveResponse) => void;
}) {
  const error =
    message.status.type === "incomplete" && message.status.reason === "error"
      ? typeof message.status.error === "string"
        ? message.status.error
        : "error"
      : null;
  const cancelled =
    message.status.type === "incomplete" && message.status.reason === "cancelled";

  return (
    <div className="self-start max-w-full flex flex-col gap-2">
      {message.content.map((part, idx) => (
        <AssistantPart
          key={`${message.id}-${idx}`}
          part={part}
          channel={channel}
          onInteractive={onInteractive}
        />
      ))}
      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <strong>Error:</strong> {error}
        </div>
      )}
      {cancelled && (
        <div className="rounded-lg border border-border bg-muted/40 px-3 py-1.5 text-[11px] text-muted-foreground">
          Cancelado por el operator.
        </div>
      )}
    </div>
  );
}

function AssistantPart({
  part,
  channel,
  onInteractive,
}: {
  part: ThreadAssistantMessagePart;
  channel: ChannelKind;
  onInteractive: (event: InteractiveResponse) => void;
}) {
  if (part.type === "text") {
    if (!part.text) return null;
    return (
      <div className="self-start max-w-[80%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2 text-sm whitespace-pre-wrap">
        {part.text}
      </div>
    );
  }
  if (part.type === "reasoning") {
    if (!part.text) return null;
    return (
      <details className="self-start max-w-[80%] rounded-lg border border-dashed border-border bg-card/40 px-3 py-2 text-xs text-muted-foreground">
        <summary className="cursor-pointer select-none text-[11px] uppercase tracking-wide">
          Razonamiento
        </summary>
        <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px]">
          {part.text}
        </pre>
      </details>
    );
  }
  if (part.type === "tool-call") {
    return (
      <div className="self-start max-w-[80%] rounded-lg border border-border bg-card/30 px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-mono font-medium">{part.toolName}</span>
          {part.result !== undefined ? (
            <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-800">
              done
            </span>
          ) : (
            <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-[10px] font-medium text-yellow-800">
              running…
            </span>
          )}
        </div>
        {part.argsText && (
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-[11px] text-muted-foreground">
            {part.argsText}
          </pre>
        )}
      </div>
    );
  }
  if (part.type === "data" && part.name === "ucm") {
    // The UCM payload comes from the backend's ucm_formatter node;
    // we trust it has the right shape (validated server-side).
    const ucm = part.data as UCMMessage;
    return channel === "whatsapp" ? (
      <WhatsAppPreview ucm={ucm} />
    ) : (
      <UCMRenderer ucm={ucm} onInteractive={onInteractive} />
    );
  }
  if (part.type === "data" && part.name === "audit") {
    const audit = part.data as { tool_name?: string; blocked_reason?: string };
    return (
      <div className="self-start max-w-[80%] rounded-lg border border-dashed border-[#ffe082] bg-[#fff8e1] px-3 py-1.5 text-[11px] text-[#7a4f00]">
        Dry-run intercepted{" "}
        <code className="font-mono">{audit.tool_name}</code>{" "}
        ({audit.blocked_reason ?? "blocked"})
      </div>
    );
  }
  return null;
}

function PendingBubble() {
  return (
    <div className="self-start max-w-[80%] rounded-2xl rounded-bl-sm bg-muted px-4 py-2 text-sm text-muted-foreground italic">
      El agente está pensando…
    </div>
  );
}

function ChannelHintFooter({ channel }: { channel: ChannelKind }) {
  return (
    <div className="border-t border-border bg-card/20 px-3 py-1.5 text-[10px] text-muted-foreground">
      Preview activo: <strong className="uppercase">{channel}</strong>. Las
      respuestas se re-renderizan al cambiar el canal — sin re-ejecutar
      el turno.
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
