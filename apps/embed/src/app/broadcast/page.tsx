"use client";

/**
 * /broadcast — the widget modal (ADR-028, Fase 1).
 *
 * Flow: handshake (auph:ready → auph:init with token + recipients) →
 * load approved templates → pick one → per-recipient preview → send →
 * live per-recipient status by polling. The audience ALWAYS comes from
 * the partner via the init payload — this modal never invents it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  createBroadcast,
  fetchBroadcast,
  fetchTemplates,
  renderPreview,
  templateBodyVars,
  type BroadcastAccepted,
  type BroadcastStatus,
  type Template,
} from "@/lib/api";
import {
  announceReady,
  connectBridge,
  postToParent,
  type InitPayload,
  type Recipient,
} from "@/lib/bridge";

type Phase =
  | { name: "handshake" }
  | { name: "loading" }
  | { name: "pick"; templates: Template[] }
  | { name: "confirm"; templates: Template[]; template: Template }
  | { name: "sending"; template: Template }
  | { name: "done"; accepted: BroadcastAccepted; live: BroadcastStatus | null }
  | { name: "error"; message: string; retry: (() => void) | null };

export default function BroadcastPage() {
  const [phase, setPhase] = useState<Phase>({ name: "handshake" });
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const initRef = useRef<InitPayload | null>(null);

  const loadTemplates = useCallback(async () => {
    setPhase({ name: "loading" });
    try {
      const { templates } = await fetchTemplates();
      setPhase({ name: "pick", templates });
    } catch (error) {
      setPhase({
        name: "error",
        message: error instanceof ApiError ? error.detail : "No se pudieron cargar las plantillas",
        retry: () => void loadTemplates(),
      });
    }
  }, []);

  useEffect(() => {
    const disconnect = connectBridge({
      onInit: (payload) => {
        initRef.current = payload;
        setRecipients(payload.recipients ?? []);
        const body = document.body;
        if (payload.appearance.colorPrimary) {
          body.style.setProperty("--auph-accent", payload.appearance.colorPrimary);
        }
        if (payload.appearance.radius) {
          body.style.setProperty("--auph-radius", payload.appearance.radius);
        }
        void loadTemplates();
      },
      onToken: () => {
        // Fresh token in memory — a phase in `error(401)` can be retried.
      },
    });
    announceReady();
    return disconnect;
  }, [loadTemplates]);

  const close = useCallback(() => postToParent("auph:close"), []);

  return (
    <div className="fixed inset-0 flex items-center justify-center p-4 sm:p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Campañas de WhatsApp"
        className="flex max-h-full w-full max-w-2xl flex-col overflow-hidden bg-surface shadow-2xl"
        style={{ borderRadius: "var(--radius-widget)" }}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <span aria-hidden className="inline-block size-2.5 rounded-full bg-accent" />
            <h1 className="text-sm font-semibold tracking-tight">Enviar campaña de WhatsApp</h1>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Cerrar"
            className="rounded-md p-1.5 text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto p-5">
          {phase.name === "handshake" && <HandshakeState />}
          {phase.name === "loading" && <LoadingState />}
          {phase.name === "pick" && (
            <TemplatePicker
              templates={phase.templates}
              recipientCount={recipients.length}
              onPick={(template) =>
                setPhase({ name: "confirm", templates: phase.templates, template })
              }
            />
          )}
          {phase.name === "confirm" && (
            <ConfirmStep
              template={phase.template}
              recipients={recipients}
              onBack={() => setPhase({ name: "pick", templates: phase.templates })}
              onSend={async () => {
                setPhase({ name: "sending", template: phase.template });
                try {
                  const accepted = await createBroadcast({
                    template_name: phase.template.name,
                    language: phase.template.language,
                    recipients: recipients.map((r) => ({
                      phone: r.phone,
                      variables: r.variables ?? {},
                    })),
                  });
                  postToParent("auph:broadcast:done", {
                    broadcastId: accepted.broadcast_id,
                    accepted: accepted.accepted,
                  });
                  setPhase({ name: "done", accepted, live: null });
                } catch (error) {
                  setPhase({
                    name: "error",
                    message:
                      error instanceof ApiError ? error.detail : "No se pudo enviar la campaña",
                    retry: null,
                  });
                }
              }}
            />
          )}
          {phase.name === "sending" && <SendingState />}
          {phase.name === "done" && (
            <ResultView
              accepted={phase.accepted}
              live={phase.live}
              onLive={(live) => setPhase({ ...phase, live })}
              onClose={close}
            />
          )}
          {phase.name === "error" && (
            <ErrorState message={phase.message} onRetry={phase.retry} onClose={close} />
          )}
        </main>
      </div>
    </div>
  );
}

/* ── states ─────────────────────────────────────────────────────────── */

function HandshakeState() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-ink-muted">
      <Spinner />
      <p className="text-sm">Conectando con tu plataforma…</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-3 py-2" aria-busy>
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-16 animate-pulse rounded-lg bg-surface-muted" />
      ))}
    </div>
  );
}

function SendingState() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-ink-muted">
      <Spinner />
      <p className="text-sm">Enviando campaña…</p>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
  onClose,
}: {
  message: string;
  onRetry: (() => void) | null;
  onClose: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-12 text-center">
      <p className="max-w-sm text-sm text-danger" role="alert">
        {message}
      </p>
      <div className="flex gap-2">
        {onRetry && (
          <button type="button" onClick={onRetry} className={buttonPrimary}>
            Reintentar
          </button>
        )}
        <button type="button" onClick={onClose} className={buttonGhost}>
          Cerrar
        </button>
      </div>
    </div>
  );
}

function TemplatePicker({
  templates,
  recipientCount,
  onPick,
}: {
  templates: Template[];
  recipientCount: number;
  onPick: (template: Template) => void;
}) {
  if (templates.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-ink-muted">
        <p className="font-medium text-ink">No hay plantillas aprobadas</p>
        <p className="mt-1 text-pretty">
          Tu proveedor debe aprobar al menos una plantilla de WhatsApp antes de poder enviar
          campañas.
        </p>
      </div>
    );
  }
  return (
    <div>
      <p className="mb-3 text-sm text-ink-muted">
        Elegí la plantilla para <strong className="text-ink">{recipientCount}</strong>{" "}
        {recipientCount === 1 ? "destinatario" : "destinatarios"}.
      </p>
      <ul className="space-y-2">
        {templates.map((template) => (
          <li key={`${template.name}:${template.language}`}>
            <button
              type="button"
              onClick={() => onPick(template)}
              className="w-full rounded-lg border border-line p-4 text-left transition-colors hover:border-accent focus-visible:outline-2 focus-visible:outline-accent"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{template.name}</span>
                <span className="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-xs text-ink-muted">
                  {template.language}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-pretty text-xs text-ink-muted">
                {template.components.find((c) => c.type?.toUpperCase() === "BODY")?.text ?? ""}
              </p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConfirmStep({
  template,
  recipients,
  onBack,
  onSend,
}: {
  template: Template;
  recipients: Recipient[];
  onBack: () => void;
  onSend: () => void;
}) {
  const requiredVars = useMemo(() => templateBodyVars(template), [template]);
  const missing = useMemo(
    () =>
      recipients.filter((r) =>
        requiredVars.some((name) => !(r.variables ?? {})[name]),
      ),
    [recipients, requiredVars],
  );
  const first = recipients[0];

  return (
    <div className="space-y-4">
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Vista previa
        </h2>
        <div className="mt-2 rounded-lg bg-surface-muted p-4">
          <p className="whitespace-pre-wrap text-pretty text-sm">
            {first ? renderPreview(template, first.variables ?? {}) : "—"}
          </p>
          {first && (
            <p className="mt-2 text-xs text-ink-muted">
              Ejemplo con los datos de {first.phone}. Cada destinatario recibe sus propios valores.
            </p>
          )}
        </div>
      </section>

      <section className="flex items-center justify-between rounded-lg border border-line px-4 py-3 text-sm">
        <span className="text-ink-muted">Destinatarios</span>
        <span className="font-medium">{recipients.length}</span>
      </section>

      {missing.length > 0 && (
        <p className="rounded-lg bg-surface-muted px-4 py-3 text-xs text-warn" role="alert">
          {missing.length} {missing.length === 1 ? "destinatario no trae" : "destinatarios no traen"}{" "}
          todas las variables de la plantilla — se rechazarán al enviar.
        </p>
      )}

      <div className="flex justify-between pt-2">
        <button type="button" onClick={onBack} className={buttonGhost}>
          ← Cambiar plantilla
        </button>
        <button
          type="button"
          onClick={onSend}
          disabled={recipients.length === 0}
          className={buttonPrimary}
        >
          Enviar a {recipients.length - missing.length}{" "}
          {recipients.length - missing.length === 1 ? "destinatario" : "destinatarios"}
        </button>
      </div>
    </div>
  );
}

function ResultView({
  accepted,
  live,
  onLive,
  onClose,
}: {
  accepted: BroadcastAccepted;
  live: BroadcastStatus | null;
  onLive: (status: BroadcastStatus) => void;
  onClose: () => void;
}) {
  // Poll delivery state while the modal stays open (dispatcher drains in seconds).
  useEffect(() => {
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const status = await fetchBroadcast(accepted.broadcast_id);
        if (!cancelled) onLive(status);
        const pending = (status.counts["pending"] ?? 0) + (status.counts["queued"] ?? 0);
        if (pending === 0) clearInterval(timer);
      } catch {
        /* transient — keep polling */
      }
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accepted.broadcast_id]);

  const counts = live?.counts ?? { queued: accepted.accepted };

  return (
    <div className="space-y-4">
      <div className="flex flex-col items-center gap-2 py-4 text-center">
        <span
          aria-hidden
          className="flex size-10 items-center justify-center rounded-full bg-surface-muted text-ok"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M4 10.5l4 4 8-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <h2 className="text-sm font-semibold">Campaña aceptada</h2>
        <p className="text-pretty text-sm text-ink-muted">
          {accepted.accepted} {accepted.accepted === 1 ? "mensaje en cola" : "mensajes en cola"}
          {accepted.rejected.length > 0 && ` · ${accepted.rejected.length} rechazados`}
        </p>
      </div>

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Object.entries(counts).map(([state, count]) => (
          <div key={state} className="rounded-lg border border-line px-3 py-2 text-center">
            <p className="text-lg font-semibold">{count}</p>
            <p className="text-xs text-ink-muted">{stateLabel(state)}</p>
          </div>
        ))}
      </section>

      {accepted.rejected.length > 0 && (
        <details className="rounded-lg border border-line px-4 py-3 text-sm">
          <summary className="cursor-pointer text-ink-muted">
            Rechazados ({accepted.rejected.length})
          </summary>
          <ul className="mt-2 space-y-1 text-xs">
            {accepted.rejected.map((r) => (
              <li key={`${r.phone}:${r.reason}`} className="flex justify-between gap-2">
                <span>{r.phone}</span>
                <span className="text-danger">{rejectLabel(r.reason)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="flex justify-end pt-2">
        <button type="button" onClick={onClose} className={buttonPrimary}>
          Listo
        </button>
      </div>
    </div>
  );
}

/* ── bits ───────────────────────────────────────────────────────────── */

const buttonPrimary =
  "rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-opacity hover:opacity-90 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const buttonGhost =
  "rounded-lg px-4 py-2 text-sm font-medium text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-accent";

function Spinner() {
  return (
    <span
      aria-hidden
      className="size-6 animate-spin rounded-full border-2 border-line border-t-accent"
    />
  );
}

function stateLabel(state: string): string {
  const labels: Record<string, string> = {
    queued: "en cola",
    pending: "en cola",
    sent: "enviados",
    delivered: "entregados",
    read: "leídos",
    failed: "fallidos",
    rejected: "rechazados",
  };
  return labels[state] ?? state;
}

function rejectLabel(reason: string): string {
  if (reason.startsWith("missing_variables")) return "faltan variables";
  const labels: Record<string, string> = {
    invalid_phone: "número inválido",
    duplicate: "duplicado",
    opted_out: "dado de baja",
  };
  return labels[reason] ?? reason;
}
