"use client";

import { CalendarClock, Clock, Info, Send, SlidersHorizontal, Zap } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Input, Label, NativeSelect, StatusBadge } from "@nexus/ui";

import {
  closePlaygroundAction,
  openPlaygroundAction,
  sendPlaygroundAction,
  setPlaygroundTimeAction,
} from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useLocale, useT } from "@/i18n/client";
import type { PlaygroundReply, PlaygroundSession, PlaygroundTurn, SimBooking } from "@/lib/backend/agent-quality-types";

import type { Result } from "./builder-model";
import { simTimeLabel, simTimeShort, wallTime } from "./quality-model";

type Ids = { ref: string; agent: string };
export type PlaygroundActions = {
  open: (body: Ids & { version?: "draft" | number; now?: string }) => Promise<Result<PlaygroundSession>>;
  send: (body: Ids & { session: string; text: string }) => Promise<Result<PlaygroundReply>>;
  setTime: (body: Ids & { session: string; now: string }) => Promise<Result<PlaygroundSession>>;
  close: (body: Ids & { session: string }) => Promise<Result<null>>;
};

const SERVER_ACTIONS: PlaygroundActions = {
  open: (body) => openPlaygroundAction(body),
  send: (body) => sendPlaygroundAction(body),
  setTime: (body) => setPlaygroundTimeAction(body),
  close: (body) => closePlaygroundAction(body),
};

const MAX_TEXT = 1000;

/**
 * El probador de la pantalla del agente (spec 047, historia 8; requisito 20),
 * como el chat del prototipo aprobado (§5.2): «Chat de prueba · así lo verá su
 * cliente», con la hora simulada en la cabecera y la conversación que empieza
 * al escribir (con el borrador, o con la versión publicada que se elija).
 *
 * Las respuestas salen como burbujas de WhatsApp y, si el agente manda más de
 * una seguida, se dice (20.4). Cada acción que habría hecho se cuenta como «Lo
 * que habría hecho: …» (20.3). Detrás de «Opciones»: qué versión probar, la
 * hora simulada en la zona del negocio (se puede cambiar), la agenda simulada
 * que cambia con lo que hace el agente (20.2) y «Nueva conversación». Nada sale
 * de aquí: ningún envío ni reserva real.
 *
 * Quien solo lee ve la última conversación de prueba sin poder escribir (20.5).
 */
export function AgentPlayground({
  refId,
  agentId,
  sessions,
  versions,
  hasDraft,
  canWrite,
  onWhy,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  agentId: string;
  /** Las conversaciones abiertas; `null` si no se pudieron leer. */
  sessions: PlaygroundSession[] | null;
  /** Las versiones publicadas que se pueden probar, la más nueva primero. */
  versions: number[];
  hasDraft: boolean;
  canWrite: boolean;
  /** «¿Por qué dijo esto?» sobre una respuesta del agente: lo explica el copiloto. */
  onWhy?: (turn: PlaygroundTurn) => void;
  actions?: PlaygroundActions;
}) {
  const t = useT();
  const locale = useLocale();
  const base = React.useId();
  const ids = { ref: refId, agent: agentId };
  const [session, setSession] = React.useState<PlaygroundSession | null>(() => sessions?.[0] ?? null);
  const [version, setVersion] = React.useState<string>(hasDraft || !versions.length ? "draft" : String(versions[0]));
  const [options, setOptions] = React.useState(false);
  const [opening, setOpening] = React.useState(false);
  const [text, setText] = React.useState("");
  const [pending, setPending] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const endRef = React.useRef<HTMLLIElement>(null);

  const writes = canWrite && (session ? session.allowed.includes("send") : true);
  const canClose = Boolean(session?.allowed.includes("close"));
  const canSetTime = Boolean(session?.allowed.includes("set_time"));
  const turns = session?.transcript ?? [];

  React.useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [turns.length, pending]);

  function failText(res: Extract<Result<unknown>, { ok: false }>): string {
    return res.code === "build_budget_exhausted" || res.status === 402
      ? t("money.build.blocked")
      : res.code === "turn_in_progress"
        ? t("builder.pg.error.busy")
        : res.code === "turn_timeout" || res.status === 504
          ? t("builder.pg.error.timeout")
          : res.status === 401 || res.status === 403
            ? t("common.forbidden")
            : t("builder.pg.error.generic");
  }

  /** Una conversación nueva con la versión elegida; la anterior se cierra. */
  async function open(): Promise<PlaygroundSession | null> {
    if (session && canClose) await actions.close({ ...ids, session: session.session_id });
    const res = await actions.open({ ...ids, version: version === "draft" ? "draft" : Number(version) });
    if (res.ok) {
      setSession(res.data);
      return res.data;
    }
    setError(failText(res));
    return null;
  }

  async function restart() {
    setOpening(true);
    setError(null);
    const next = await open();
    setOpening(false);
    if (next) setOptions(false);
  }

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message || pending) return;
    setPending(message);
    setError(null);
    // Como el prototipo: sin conversación abierta, la abre el primer mensaje.
    const current = session ?? (await open());
    if (!current) {
      setPending(null);
      return;
    }
    const res = await actions.send({ ...ids, session: current.session_id, text: message });
    setPending(null);
    if (res.ok) {
      setText("");
      setSession({
        ...current,
        now: res.data.now,
        agenda: res.data.agenda,
        transcript: [...current.transcript, { role: "customer", bubbles: [message], several_bubbles: false, actions: [] }, res.data.turn],
      });
      return;
    }
    if (res.code === "unknown_session") {
      setSession(null);
      setError(t("builder.pg.error.gone"));
      return;
    }
    setError(failText(res));
  }

  const showOptions = canWrite || session !== null;

  return (
    <section aria-labelledby={`${base}-title`} className="grid min-w-0 overflow-hidden rounded-lg border border-border bg-card" data-slot="agent-playground">
      <div className="flex min-w-0 items-center justify-between gap-2 border-b border-border px-3 py-2">
        <h2 id={`${base}-title`} className="min-w-0 text-sm font-medium text-pretty">
          {t("agentProto.chat.title")}
        </h2>
        <div className="flex shrink-0 items-center gap-1">
          {session ? (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground tabular-nums" data-slot="playground-clock">
              <Clock aria-hidden="true" className="size-3" />
              <span className="sr-only">{t("builder.pg.time")}: </span>
              {simTimeShort(session.now, session.timezone, locale)}
            </span>
          ) : null}
          {showOptions ? (
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label={t("agentProto.chat.options")}
              aria-expanded={options}
              aria-controls={`${base}-options`}
              onClick={() => setOptions((v) => !v)}
            >
              <SlidersHorizontal aria-hidden="true" />
            </Button>
          ) : null}
        </div>
      </div>

      {options ? (
        <div id={`${base}-options`} className="grid min-w-0 gap-3 border-b border-border p-3" data-slot="playground-options">
          {session ? (
            <StatusBadge tone={session.is_draft ? "info" : "positive"}>
              {session.is_draft ? t("builder.pg.testing.draft", { n: session.version_number }) : t("builder.pg.testing.version", { n: session.version_number })}
            </StatusBadge>
          ) : null}
          {canWrite ? (
            <div className="grid min-w-0 gap-2" data-slot="playground-start">
              <Label htmlFor={`${base}-version`}>{t("builder.pg.version")}</Label>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <NativeSelect id={`${base}-version`} value={version} onChange={(e) => setVersion(e.target.value)} wrapperClassName="min-w-32 flex-1">
                  {hasDraft || !versions.length ? <option value="draft">{t("builder.pg.version.draft")}</option> : null}
                  {versions.map((n) => (
                    <option key={n} value={String(n)}>
                      {t("builder.pg.version.number", { n })}
                    </option>
                  ))}
                </NativeSelect>
                <Button type="button" size="sm" variant="outline" onClick={() => void restart()} loading={opening}>
                  {t("builder.pg.new")}
                </Button>
              </div>
            </div>
          ) : null}
          {session ? <SimPanel session={session} ids={ids} canSetTime={canSetTime} actions={actions} onChange={setSession} /> : null}
        </div>
      ) : null}

      <ol
        aria-label={t("builder.pg.chat")}
        aria-live="polite"
        className="flex h-[300px] min-w-0 flex-col gap-2 overflow-y-auto bg-(--chat-bg) p-4"
        data-slot="playground-chat"
      >
        {!turns.length && !pending ? (
          <SystemNote icon={<Info aria-hidden="true" className="mt-px size-3 shrink-0" />}>
            {canWrite ? t("agentProto.chat.empty") : t("builder.pg.none")}
          </SystemNote>
        ) : null}
        {turns.map((turn, i) => (
          <Turn key={i} turn={turn} onWhy={onWhy} />
        ))}
        {pending ? (
          <>
            <Turn turn={{ role: "customer", bubbles: [pending], several_bubbles: false, actions: [] }} />
            <li className="text-xs text-muted-foreground" role="status">
              {t("builder.pg.typing")}
            </li>
          </>
        ) : null}
        <li ref={endRef} aria-hidden="true" className="h-0 shrink-0" />
      </ol>

      {writes ? (
        <form onSubmit={send} className="flex min-w-0 items-center gap-2 border-t border-border p-3" data-slot="playground-form">
          <Label htmlFor={`${base}-text`} className="sr-only">
            {t("builder.pg.message")}
          </Label>
          <Input
            id={`${base}-text`}
            value={text}
            maxLength={MAX_TEXT}
            autoComplete="off"
            placeholder={t("agentProto.chat.placeholder")}
            onChange={(e) => setText(e.target.value)}
            className="min-w-0 flex-1"
          />
          <Button type="submit" size="icon" loading={pending !== null} aria-label={t("builder.pg.send")} className="shrink-0">
            <Send aria-hidden="true" />
          </Button>
        </form>
      ) : (
        <p className="border-t border-border px-3 py-2 text-xs text-pretty text-muted-foreground">{t("builder.pg.readonly")}</p>
      )}
      {error ? (
        <p role="alert" className="px-3 pb-3 text-xs text-destructive text-pretty">
          {error}
        </p>
      ) : null}
    </section>
  );
}

/** Una nota del sistema en el chat: centrada, con borde discontinuo (§5.2). */
function SystemNote({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <li className="flex max-w-[94%] min-w-0 items-start gap-2 self-center rounded-lg border border-dashed border-input bg-card px-3 py-2 text-xs text-pretty text-muted-foreground">
      {icon}
      <span className="min-w-0">{children}</span>
    </li>
  );
}

/** Una burbuja por mensaje, como en WhatsApp: el cliente a la derecha, el agente a la izquierda. */
function Turn({ turn, onWhy }: { turn: PlaygroundTurn; onWhy?: (turn: PlaygroundTurn) => void }) {
  const t = useT();
  const mine = turn.role === "customer";
  const who = mine ? t("builder.pg.customer") : t("builder.pg.agent");
  return (
    <li className={`flex min-w-0 shrink-0 flex-col gap-1 ${mine ? "items-end" : "items-start"}`} data-slot="playground-turn" data-role={turn.role}>
      <span className="sr-only">{who}</span>
      {turn.bubbles.map((bubble, i) => (
        <p
          key={i}
          className={`max-w-[82%] rounded-lg px-3 py-2 text-sm/snug text-pretty break-words whitespace-pre-line text-foreground shadow-xs ${
            mine ? "bg-(--bubble-out)" : "bg-card"
          }`}
          data-slot="playground-bubble"
        >
          {bubble}
        </p>
      ))}
      {!mine && turn.several_bubbles ? (
        <span className="text-xs text-muted-foreground" data-slot="playground-several">
          {t("builder.pg.several", { n: turn.bubbles.length })}
        </span>
      ) : null}
      {!mine && turn.actions.length ? (
        <ul className="grid max-w-[94%] min-w-0 gap-1 self-center" data-slot="playground-actions">
          {turn.actions.map((a, i) => (
            <li key={i} className="flex min-w-0 items-start gap-2 rounded-lg border border-dashed border-input bg-card px-3 py-2 text-xs text-pretty text-muted-foreground">
              <Zap aria-hidden="true" className="mt-px size-3 shrink-0" />
              <span className="min-w-0">{t("builder.pg.would", { phrase: a.phrase })}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {!mine && onWhy ? (
        <Button type="button" variant="ghost" size="xs" onClick={() => onWhy(turn)} data-slot="playground-why">
          {t("builder.copilot.why")}
        </Button>
      ) : null}
    </li>
  );
}

/** La hora y la agenda simuladas (20.2): la hora se dice en la zona del negocio. */
function SimPanel({
  session,
  ids,
  canSetTime,
  actions,
  onChange,
}: {
  session: PlaygroundSession;
  ids: Ids;
  canSetTime: boolean;
  actions: PlaygroundActions;
  onChange: (session: PlaygroundSession) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const base = React.useId();
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(() => wallTime(session.now, session.timezone));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!value) return;
    setBusy(true);
    setError(null);
    const res = await actions.setTime({ ...ids, session: session.session_id, now: value.length === 16 ? `${value}:00` : value });
    setBusy(false);
    if (res.ok) {
      onChange({ ...session, now: res.data.now, agenda: res.data.agenda });
      setEditing(false);
      toast.success(t("builder.pg.time.saved"));
      return;
    }
    setError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.pg.error.generic"));
  }

  return (
    <div className="grid min-w-0 gap-3 rounded-md border border-border p-3" data-slot="playground-sim">
      <div className="grid min-w-0 gap-1">
        <p className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <CalendarClock aria-hidden="true" className="size-4" />
          {t("builder.pg.time")}
        </p>
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium tabular-nums" data-slot="playground-now">
            {simTimeLabel(session.now, session.timezone, locale)}
          </p>
          {canSetTime && !editing ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setValue(wallTime(session.now, session.timezone));
                setEditing(true);
              }}
            >
              {t("builder.pg.time.change")}
            </Button>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">{t("builder.pg.time.zone", { zone: session.timezone })}</p>
        {editing ? (
          <form onSubmit={save} className="grid min-w-0 gap-2">
            <Label htmlFor={`${base}-time`}>{t("builder.pg.time.input")}</Label>
            <Input id={`${base}-time`} type="datetime-local" value={value} required onChange={(e) => setValue(e.target.value)} />
            {error ? (
              <p role="alert" className="text-xs text-destructive">
                {error}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" size="sm" loading={busy}>
                {t("builder.pg.time.save")}
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
                {t("builder.pg.time.cancel")}
              </Button>
            </div>
          </form>
        ) : null}
      </div>
      <div className="grid min-w-0 gap-2">
        <p className="text-xs font-medium text-muted-foreground" id={`${base}-agenda`}>
          {t("builder.pg.agenda")}
        </p>
        {session.agenda.length ? (
          <ul aria-labelledby={`${base}-agenda`} className="grid min-w-0 gap-1" data-slot="playground-agenda">
            {session.agenda.map((b) => (
              <Booking key={b.id} booking={b} />
            ))}
          </ul>
        ) : (
          <p className="text-xs text-pretty text-muted-foreground">{t("builder.pg.agenda.empty")}</p>
        )}
      </div>
    </div>
  );
}

function Booking({ booking }: { booking: SimBooking }) {
  const t = useT();
  const cancelled = booking.status === "cancelled";
  return (
    <li className="flex min-w-0 flex-wrap items-center justify-between gap-2 text-sm">
      <span className={`min-w-0 break-words ${cancelled ? "text-muted-foreground line-through" : ""}`}>
        {booking.service} · {booking.when}
      </span>
      <StatusBadge tone={cancelled ? "muted" : "positive"}>{cancelled ? t("builder.pg.agenda.cancelled") : t("builder.pg.agenda.confirmed")}</StatusBadge>
    </li>
  );
}
