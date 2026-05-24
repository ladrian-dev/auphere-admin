/**
 * Rich message bubble — Bloque B (operator observability).
 *
 * Renders one ``MessageOut`` row with the full observability stack
 * the operator needs to debug a turn at a glance:
 *
 * - Header: direction · intent · model · datetime · delivery status badge.
 * - Quoted-reply chip (when ``context_message_id`` is set).
 * - Body: plain content text.
 * - **Interactive component preview** (B1): buttons / list / cta_url
 *   rendered as visual chips, not as raw JSON.
 * - **Media preview** (B1): icon + filename + size for image/audio/
 *   video/document outbounds.
 * - **Reaction line**: emoji + the wamid being reacted to.
 * - **Tool calls panel** (B2): per-call name + status + JSON args/result,
 *   color-coded by status (ok / skipped / error).
 * - **Outcome grader badge** (B3): pass/fail/skipped/error with the
 *   feedback string on hover when failed.
 * - **Footer** (B5): latency + cost + provider_message_id for support.
 *
 * The component is read-only — no actions. Pause / takeover lives in
 * the page header (existing ``AgentToggle``); per-message intervention
 * (e.g. "respond as operator on this thread") is Bloque C.
 */

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  InteractivePayload,
  MessageOut,
  MessageStatus,
  OutcomeVerdict,
} from "@/lib/backend";
import {
  formatBytes,
  formatCostUsd,
  formatLatency,
  fullDateTime,
} from "@/lib/format";

export function MessageBubble({ message }: { message: MessageOut }) {
  const inbound = message.direction === "inbound";
  return (
    <div
      className={
        "flex flex-col gap-2 rounded-md border border-border px-3 py-2 " +
        (inbound ? "bg-blue-50/50 dark:bg-blue-950/20" : "bg-muted/40")
      }
      data-testid={`message-bubble-${message.id}`}
    >
      <MessageHeader message={message} inbound={inbound} />
      {message.context_message_id ? (
        <QuotedReplyChip wamid={message.context_message_id} />
      ) : null}
      {message.content ? (
        <p className="text-sm whitespace-pre-wrap break-words">
          {message.content}
        </p>
      ) : null}
      {message.interactive_payload ? (
        <InteractivePreview payload={message.interactive_payload} />
      ) : null}
      {message.media_kind ? <MediaPreview message={message} /> : null}
      {message.reaction_emoji ? (
        <ReactionLine
          emoji={message.reaction_emoji}
          wamid={message.reaction_target_wamid}
        />
      ) : null}
      {message.tool_calls.length > 0 ? (
        <ToolCallsPanel calls={message.tool_calls} />
      ) : null}
      <MessageFooter message={message} />
    </div>
  );
}

// ── header ────────────────────────────────────────────────────────────

function MessageHeader({
  message,
  inbound,
}: {
  message: MessageOut;
  inbound: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-[10px] font-mono uppercase text-muted-foreground tabular-nums">
      <span
        className="flex items-center gap-2 flex-wrap"
        style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      >
        <span>{inbound ? "← Cliente" : "→ Agente"}</span>
        {message.intent ? <span>· {message.intent}</span> : null}
        {message.model ? <span>· {message.model}</span> : null}
        {!inbound ? <StatusBadge status={message.status} /> : null}
        {message.outcome_overall ? (
          <OutcomeBadge
            verdict={message.outcome_overall}
            retries={message.outcome_retries}
            feedback={message.outcome_feedback}
          />
        ) : null}
      </span>
      <span>{fullDateTime(message.created_at)}</span>
    </div>
  );
}

const STATUS_VARIANTS: Record<
  MessageStatus,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  pending: { label: "Pendiente", variant: "outline" },
  sent: { label: "Enviado", variant: "secondary" },
  delivered: { label: "Entregado", variant: "default" },
  read: { label: "Leído", variant: "default" },
  failed: { label: "Falló", variant: "destructive" },
};

function StatusBadge({ status }: { status: MessageStatus }) {
  const spec = STATUS_VARIANTS[status] ?? STATUS_VARIANTS.pending;
  return (
    <Badge variant={spec.variant} className="text-[10px] uppercase">
      {spec.label}
    </Badge>
  );
}

// ── outcome grader badge (B3) ─────────────────────────────────────────

const OUTCOME_VARIANTS: Record<
  OutcomeVerdict,
  { label: string; className: string }
> = {
  pass: {
    label: "Pass",
    className:
      "border-emerald-500/40 bg-emerald-100/60 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200",
  },
  fail: {
    label: "Fail",
    className:
      "border-red-500/40 bg-red-100/60 text-red-900 dark:bg-red-950/40 dark:text-red-200",
  },
  skipped: {
    label: "Skipped",
    className: "border-muted-foreground/30 text-muted-foreground",
  },
  error: {
    label: "Error",
    className:
      "border-amber-500/40 bg-amber-100/60 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
  },
};

function OutcomeBadge({
  verdict,
  retries,
  feedback,
}: {
  verdict: OutcomeVerdict;
  retries: number | null;
  feedback: string | null;
}) {
  const spec = OUTCOME_VARIANTS[verdict] ?? OUTCOME_VARIANTS.skipped;
  const trigger = (
    <span
      className={
        "rounded-full border px-2 py-0.5 text-[10px] uppercase font-medium " +
        spec.className
      }
      data-testid={`outcome-badge-${verdict}`}
    >
      {spec.label}
      {retries && retries > 0 ? (
        <span className="ml-1 opacity-70">· r{retries}</span>
      ) : null}
    </span>
  );
  if (!feedback) return trigger;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger render={trigger} />
        <TooltipContent className="max-w-sm text-xs">
          {feedback}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ── quoted reply chip ─────────────────────────────────────────────────

function QuotedReplyChip({ wamid }: { wamid: string }) {
  return (
    <div className="text-[11px] text-muted-foreground italic border-l-2 border-muted-foreground/30 pl-2">
      ↪ respondiendo a{" "}
      <code className="font-mono text-[10px]">{wamid.slice(0, 24)}…</code>
    </div>
  );
}

// ── interactive preview (B1) ──────────────────────────────────────────

function InteractivePreview({ payload }: { payload: InteractivePayload }) {
  return (
    <div
      className="grid gap-2 rounded-md border border-dashed border-muted-foreground/30 bg-background/60 p-2"
      data-testid="interactive-preview"
    >
      <span className="text-[10px] font-mono uppercase text-muted-foreground">
        Componente interactivo
      </span>
      {payload.header ? (
        <p className="text-xs font-semibold">{payload.header}</p>
      ) : null}
      <p className="text-sm">{payload.body}</p>
      {payload.buttons ? <ButtonsRow buttons={payload.buttons} /> : null}
      {payload.list ? <ListPreview list={payload.list} /> : null}
      {payload.cta_url ? <CtaUrlPreview cta={payload.cta_url} /> : null}
      {payload.footer ? (
        <p className="text-[11px] text-muted-foreground italic">
          {payload.footer}
        </p>
      ) : null}
    </div>
  );
}

function ButtonsRow({
  buttons,
}: {
  buttons: NonNullable<InteractivePayload["buttons"]>;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {buttons.map((b) => (
        <span
          key={b.id}
          className="rounded-full border border-input bg-background px-2.5 py-0.5 text-xs"
          data-testid="interactive-button"
        >
          {b.title}
        </span>
      ))}
    </div>
  );
}

function ListPreview({
  list,
}: {
  list: NonNullable<InteractivePayload["list"]>;
}) {
  return (
    <div className="grid gap-1">
      <span className="text-[10px] font-mono uppercase text-muted-foreground">
        Botón: {list.button} · {list.items.length} ítems
      </span>
      <ul className="grid gap-0.5">
        {list.items.slice(0, 6).map((item) => (
          <li
            key={item.id}
            className="rounded-sm bg-muted/60 px-2 py-1 text-xs"
            data-testid="interactive-list-item"
          >
            <strong>{item.title}</strong>
            {item.description ? (
              <span className="text-muted-foreground"> — {item.description}</span>
            ) : null}
          </li>
        ))}
        {list.items.length > 6 ? (
          <li className="text-[11px] italic text-muted-foreground">
            +{list.items.length - 6} más
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function CtaUrlPreview({
  cta,
}: {
  cta: NonNullable<InteractivePayload["cta_url"]>;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="rounded-md border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs font-medium"
        data-testid="interactive-cta-url"
      >
        {cta.text}
      </span>
      <code className="text-[11px] text-muted-foreground truncate">
        {cta.url}
      </code>
    </div>
  );
}

// ── media preview (B1) ────────────────────────────────────────────────

const MEDIA_ICONS: Record<string, string> = {
  image: "🖼️",
  audio: "🎙️",
  video: "🎞️",
  document: "📄",
};

function MediaPreview({ message }: { message: MessageOut }) {
  const kind = message.media_kind ?? "document";
  const icon = MEDIA_ICONS[kind] ?? "📎";
  return (
    <div
      className="flex items-center gap-2 rounded-md bg-muted/50 px-2 py-1.5"
      data-testid={`media-preview-${kind}`}
    >
      <span className="text-base" aria-hidden="true">
        {icon}
      </span>
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-xs font-medium truncate">
          {message.media_filename ?? `[${kind}]`}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {message.media_mime ?? "—"} · {formatBytes(message.media_size_bytes)}
        </span>
      </div>
      {message.media_transcript ? (
        <details className="ml-auto text-[10px] text-muted-foreground">
          <summary className="cursor-pointer">Transcripción</summary>
          <p className="mt-1 max-w-sm whitespace-pre-wrap text-xs italic">
            {message.media_transcript}
          </p>
        </details>
      ) : null}
    </div>
  );
}

// ── reaction line ─────────────────────────────────────────────────────

function ReactionLine({
  emoji,
  wamid,
}: {
  emoji: string;
  wamid: string | null;
}) {
  return (
    <div
      className="flex items-center gap-2 text-xs text-muted-foreground"
      data-testid="reaction-line"
    >
      <span className="text-lg leading-none">{emoji}</span>
      {wamid ? (
        <span>
          reaccionó a{" "}
          <code className="font-mono text-[10px]">{wamid.slice(0, 16)}…</code>
        </span>
      ) : (
        <span>reacción</span>
      )}
    </div>
  );
}

// ── tool calls panel (B2) ─────────────────────────────────────────────

type ToolEnvelope = {
  tool?: string;
  intent?: string;
  status?: string;
  error?: string;
  result?: Record<string, unknown>;
};

const TOOL_STATUS_TONE: Record<string, string> = {
  ok: "border-emerald-500/30 bg-emerald-50/40 dark:bg-emerald-950/20",
  "skipped:not_in_whitelist":
    "border-amber-500/30 bg-amber-50/40 dark:bg-amber-950/20",
  "skipped:dry_run":
    "border-amber-500/30 bg-amber-50/40 dark:bg-amber-950/20",
  error: "border-red-500/30 bg-red-50/40 dark:bg-red-950/20",
};

function ToolCallsPanel({ calls }: { calls: Array<Record<string, unknown>> }) {
  return (
    <details
      className="text-xs text-muted-foreground"
      data-testid="tool-calls-panel"
    >
      <summary className="cursor-pointer font-mono">
        {calls.length} tool call{calls.length === 1 ? "" : "s"}
      </summary>
      <div className="mt-2 grid gap-2">
        {calls.map((raw, idx) => {
          const envelope = raw as ToolEnvelope;
          const status = envelope.status ?? "ok";
          const tone =
            TOOL_STATUS_TONE[status] ??
            "border-border bg-muted/30";
          return (
            <div
              key={idx}
              className={"rounded-md border px-2 py-1.5 " + tone}
              data-testid="tool-call-entry"
            >
              <div className="flex items-center justify-between gap-2 text-[11px]">
                <span className="font-mono font-medium">
                  {envelope.tool ?? "(unnamed)"}
                </span>
                <span className="font-mono uppercase tracking-wider text-[10px]">
                  {status}
                </span>
              </div>
              {envelope.error ? (
                <p className="mt-1 text-red-700 dark:text-red-300">
                  {envelope.error}
                </p>
              ) : null}
              {envelope.result &&
              Object.keys(envelope.result).length > 0 ? (
                <pre className="mt-1 overflow-x-auto rounded bg-background/60 p-1.5 text-[10px] leading-tight">
                  {JSON.stringify(envelope.result, null, 2)}
                </pre>
              ) : null}
            </div>
          );
        })}
      </div>
    </details>
  );
}

// ── footer (B5) ───────────────────────────────────────────────────────

function MessageFooter({ message }: { message: MessageOut }) {
  const hasTelemetry =
    message.latency_ms !== null ||
    message.cost_usd !== null ||
    message.provider_message_id !== null ||
    message.attempts > 1 ||
    message.failure_code !== null;
  if (!hasTelemetry) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono text-muted-foreground tabular-nums border-t border-border/50 pt-1">
      {message.latency_ms !== null ? (
        <span>⏱ {formatLatency(message.latency_ms)}</span>
      ) : null}
      {message.cost_usd !== null ? (
        <span>💰 {formatCostUsd(message.cost_usd)}</span>
      ) : null}
      {message.attempts > 1 ? (
        <span title="Intentos de envío">⟲ {message.attempts}</span>
      ) : null}
      {message.failure_code ? (
        <span
          className="text-red-700 dark:text-red-300"
          title={message.last_error ?? undefined}
        >
          err:{message.failure_code}
        </span>
      ) : null}
      {message.provider_message_id ? (
        <span className="truncate" title={message.provider_message_id}>
          wamid:{message.provider_message_id.slice(0, 12)}…
        </span>
      ) : null}
    </div>
  );
}
