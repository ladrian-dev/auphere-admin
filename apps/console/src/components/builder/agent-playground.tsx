"use client";

import { CalendarClock, Send } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Input, Label, NativeSelect, StatusBadge, Textarea } from "@nexus/ui";

import {
  closePlaygroundAction,
  openPlaygroundAction,
  sendPlaygroundAction,
  setPlaygroundTimeAction,
} from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useLocale, useT } from "@/i18n/client";
import type { PlaygroundReply, PlaygroundSession, PlaygroundTurn, SimBooking } from "@/lib/backend/agent-quality-types";

import type { Result } from "./builder-model";
import { simTimeLabel, wallTime } from "./quality-model";

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
 * El probador de la pantalla del agente (spec 047, historia 8; requisito 20):
 * conversar con el borrador —o con una versión publicada que se elija— como si
 * fuera un cliente. Las respuestas salen como burbujas de WhatsApp y, si el
 * agente manda más de una seguida, se dice (20.4). Cada acción que habría hecho
 * se cuenta como «Lo que habría hecho: …» (20.3). Encima, la hora simulada en
 * la zona del negocio (se puede cambiar) y la agenda simulada, que cambia con
 * lo que hace el agente (20.2). Nada sale de aquí: ningún envío ni reserva real.
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
  const base = React.useId();
  const ids = { ref: refId, agent: agentId };
  const [session, setSession] = React.useState<PlaygroundSession | null>(() => sessions?.[0] ?? null);
  const [choosing, setChoosing] = React.useState(false);
  const [version, setVersion] = React.useState<string>(hasDraft || !versions.length ? "draft" : String(versions[0]));
  const [opening, setOpening] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const writes = canWrite && (session ? session.allowed.includes("send") : true);
  const canClose = Boolean(session?.allowed.includes("close"));
  const canSetTime = Boolean(session?.allowed.includes("set_time"));

  async function start() {
    setOpening(true);
    setError(null);
    if (session && canClose) await actions.close({ ...ids, session: session.session_id });
    const res = await actions.open({ ...ids, version: version === "draft" ? "draft" : Number(version) });
    setOpening(false);
    if (res.ok) {
      setSession(res.data);
      setChoosing(false);
      return;
    }
    setError(
      res.code === "build_budget_exhausted" || res.status === 402
        ? t("money.build.blocked")
        : res.status === 401 || res.status === 403
          ? t("common.forbidden")
          : t("builder.pg.error.generic"),
    );
  }

  const showStart = canWrite && (!session || choosing);

  return (
    <section aria-labelledby={`${base}-title`} className="grid min-w-0 gap-4" data-slot="agent-playground">
      <div className="grid min-w-0 gap-1">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <h3 id={`${base}-title`} className="text-base font-semibold">
            {t("builder.pg.title")}
          </h3>
          {session ? (
            <StatusBadge tone={session.is_draft ? "info" : "positive"}>
              {session.is_draft ? t("builder.pg.testing.draft", { n: session.version_number }) : t("builder.pg.testing.version", { n: session.version_number })}
            </StatusBadge>
          ) : null}
        </div>
        <p className="text-sm text-pretty text-muted-foreground">{t("builder.pg.intro")}</p>
        {!canWrite ? <p className="text-xs text-muted-foreground">{t("builder.pg.readonly")}</p> : null}
      </div>

      {showStart ? (
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
            <Button type="button" onClick={() => void start()} loading={opening}>
              {t("builder.pg.start")}
            </Button>
            {session ? (
              <Button type="button" variant="ghost" onClick={() => setChoosing(false)} disabled={opening}>
                {t("builder.pg.time.cancel")}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}

      {session ? (
        <PlaygroundSessionView
          key={session.session_id}
          session={session}
          ids={ids}
          writes={writes}
          canSetTime={canSetTime}
          actions={actions}
          onWhy={onWhy}
          onChange={setSession}
          onExpired={() => {
            setSession(null);
            setError(t("builder.pg.error.gone"));
          }}
        />
      ) : !canWrite ? (
        <p className="text-sm text-pretty text-muted-foreground">{t("builder.pg.none")}</p>
      ) : null}

      {session && canWrite && !choosing ? (
        <div>
          <Button type="button" variant="outline" size="sm" onClick={() => setChoosing(true)}>
            {t("builder.pg.new")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function PlaygroundSessionView({
  session,
  ids,
  writes,
  canSetTime,
  actions,
  onWhy,
  onChange,
  onExpired,
}: {
  session: PlaygroundSession;
  ids: Ids;
  writes: boolean;
  canSetTime: boolean;
  actions: PlaygroundActions;
  onWhy?: (turn: PlaygroundTurn) => void;
  onChange: (session: PlaygroundSession) => void;
  onExpired: () => void;
}) {
  const t = useT();
  const base = React.useId();
  const [text, setText] = React.useState("");
  const [pending, setPending] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const endRef = React.useRef<HTMLLIElement>(null);
  const turns = session.transcript;

  React.useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [turns.length, pending]);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (!message || pending) return;
    setPending(message);
    setError(null);
    const res = await actions.send({ ...ids, session: session.session_id, text: message });
    setPending(null);
    if (res.ok) {
      setText("");
      onChange({
        ...session,
        now: res.data.now,
        agenda: res.data.agenda,
        transcript: [...turns, { role: "customer", bubbles: [message], several_bubbles: false, actions: [] }, res.data.turn],
      });
      return;
    }
    if (res.code === "unknown_session") return onExpired();
    setError(
      res.code === "build_budget_exhausted" || res.status === 402
        ? t("money.build.blocked")
        : res.code === "turn_in_progress"
        ? t("builder.pg.error.busy")
        : res.code === "turn_timeout" || res.status === 504
          ? t("builder.pg.error.timeout")
          : res.status === 401 || res.status === 403
            ? t("common.forbidden")
            : t("builder.pg.error.generic"),
    );
  }

  return (
    <div className="grid min-w-0 gap-4">
      <SimPanel session={session} ids={ids} canSetTime={canSetTime} actions={actions} onChange={onChange} />

      <div className="grid min-w-0 gap-3 rounded-md border border-border bg-muted/40 p-3">
        <ol aria-label={t("builder.pg.chat")} aria-live="polite" className="grid max-h-[28rem] min-w-0 gap-3 overflow-y-auto" data-slot="playground-chat">
          {!turns.length && !pending ? <li className="text-sm text-pretty text-muted-foreground">{t("builder.pg.chat.empty")}</li> : null}
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
          <li ref={endRef} aria-hidden="true" className="h-0" />
        </ol>

        {writes ? (
          <form onSubmit={send} className="grid min-w-0 gap-2" data-slot="playground-form">
            <Label htmlFor={`${base}-text`} className="sr-only">
              {t("builder.pg.message")}
            </Label>
            <div className="flex min-w-0 items-end gap-2">
              <Textarea
                id={`${base}-text`}
                value={text}
                rows={2}
                maxLength={MAX_TEXT}
                placeholder={t("builder.pg.message")}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    e.currentTarget.form?.requestSubmit();
                  }
                }}
                className="min-h-10 flex-1 bg-background"
              />
              <Button type="submit" loading={pending !== null} className="shrink-0">
                <Send aria-hidden="true" />
                {t("builder.pg.send")}
              </Button>
            </div>
            {error ? (
              <p role="alert" className="text-xs text-destructive text-pretty">
                {error}
              </p>
            ) : null}
          </form>
        ) : null}
      </div>
    </div>
  );
}

/** Una burbuja por mensaje, como en WhatsApp: el cliente a la derecha, el agente a la izquierda. */
function Turn({ turn, onWhy }: { turn: PlaygroundTurn; onWhy?: (turn: PlaygroundTurn) => void }) {
  const t = useT();
  const mine = turn.role === "customer";
  const who = mine ? t("builder.pg.customer") : t("builder.pg.agent");
  return (
    <li className={`grid min-w-0 gap-1 ${mine ? "justify-items-end" : "justify-items-start"}`} data-slot="playground-turn" data-role={turn.role}>
      <span className="sr-only">{who}</span>
      {turn.bubbles.map((bubble, i) => (
        <p
          key={i}
          className={`max-w-[85%] rounded-md px-3 py-2 text-sm text-pretty break-words whitespace-pre-line shadow-sm ${
            mine ? "bg-primary text-primary-foreground" : "bg-card text-card-foreground ring-1 ring-foreground/10"
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
        <ul className="grid max-w-[85%] min-w-0 gap-1" data-slot="playground-actions">
          {turn.actions.map((a, i) => (
            <li key={i} className="rounded-md border border-dashed border-border bg-background px-2 py-1 text-xs text-pretty">
              {t("builder.pg.would", { phrase: a.phrase })}
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
