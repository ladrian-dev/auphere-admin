"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, ConfirmDialog, NativeSelect, Section, Skeleton } from "@nexus/ui";

import { calendarAccountAction, staffCalendarAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { CalendarAccount, StaffCalendar, StaffMember } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { useActionLoad } from "../model/use-load";
import { failureMessage } from "../model/vocab";
import { Initials } from "../shared";

/** `last_error` is a code of ours; one this screen doesn't know yet gets the general sentence. */
const STATE_OF_ERROR: Record<string, MessageKey> = {
  read: "reservas.calendar.state.read",
  write: "reservas.calendar.state.write",
  calendar_gone: "reservas.calendar.state.gone",
};

const SAVE_FAILURES: Record<string, MessageKey> = {
  unknown_calendar: "reservas.calendar.fail.unknown",
  calendar_not_connected: "reservas.calendar.fail.notConnected",
  calendar_unavailable: "reservas.calendar.fail.unavailable",
};

type SaveResult = Awaited<ReturnType<typeof staffCalendarAction>>;

/**
 * Spec 043 (R10.1): each person's Google calendar. The connection itself is made
 * by whoever manages the agents: a client's person has no screen for it.
 *
 * What the API says and what this says back: no connector, a connection to redo,
 * Google not answering and an account with nothing to write to are four different
 * things, and none of them is painted as an empty list.
 */
export function StaffCalendarsSection() {
  const { t } = useReservas();
  const [attempt, setAttempt] = React.useState(0);
  // Async, so a read that throws reaches the error state instead of a stray timer.
  const account = useActionLoad(`calendar-account-${attempt}`, async () => calendarAccountAction());
  return (
    <Section title={t("reservas.calendar.title")} description={t("reservas.calendar.body")}>
      {account.kind === "ok" ? (
        <Loaded account={account.data} />
      ) : account.kind === "error" ? (
        <Failed onRetry={() => setAttempt((n) => n + 1)} />
      ) : (
        <Loading />
      )}
    </Section>
  );
}

function Loading() {
  const { t, data } = useReservas();
  const rows = Math.min(Math.max(data.staff?.length ?? 2, 1), 4);
  return (
    <div role="status" aria-label={t("reservas.calendar.loading")} className="flex min-w-0 flex-col gap-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

function Failed({ onRetry }: { onRetry: () => void }) {
  const { t } = useReservas();
  return (
    <>
      <Callout
        tone="danger"
        action={
          <Button size="xs" variant="outline" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        }
      >
        {t("reservas.calendar.loadError")}
      </Callout>
      <People calendars={[]} canPick={false} />
    </>
  );
}

function Loaded({ account }: { account: CalendarAccount }) {
  const { t, data } = useReservas();
  const linked = (data.staff ?? []).some((s) => s.calendar.status !== "none");
  const usable = account.connection === "connected" && !account.unavailable;
  return (
    <>
      {account.connection === "none" ? <Callout tone="info">{t("reservas.calendar.notConnected")}</Callout> : null}
      {account.connection === "needs_reauth" ? <Callout tone="warning">{t("reservas.calendar.reauth")}</Callout> : null}
      {account.connection === "connected" && account.unavailable ? <Callout tone="warning">{t("reservas.calendar.unavailable")}</Callout> : null}
      {usable && account.calendars.length === 0 ? <Callout tone="info">{t("reservas.calendar.noCalendars")}</Callout> : null}
      {account.connection === "none" && !linked ? null : <People calendars={account.calendars} canPick={usable && account.calendars.length > 0} />}
    </>
  );
}

function People({ calendars, canPick }: { calendars: CalendarAccount["calendars"]; canPick: boolean }) {
  const { t, data, refresh } = useReservas();
  const [letting, setLetting] = React.useState<StaffMember | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const staff = data.staff;
  if (staff === null) return <p className="text-sm text-muted-foreground">{t("reservas.settings.partError")}</p>;
  if (staff.length === 0) return <p className="text-sm text-muted-foreground">{t("reservas.calendar.noTeam")}</p>;
  return (
    <>
      <ul className="flex min-w-0 flex-col divide-y divide-border">
        {staff.map((s) => (
          <PersonRow key={s.id} member={s} calendars={calendars} canPick={canPick} onDisconnect={() => setLetting(s)} />
        ))}
      </ul>
      <ConfirmDialog
        open={letting !== null}
        onOpenChange={(o) => {
          if (!o) {
            setLetting(null);
            setError(null);
          }
        }}
        title={letting ? t("reservas.calendar.disconnect.title", { name: letting.name }) : ""}
        description={t("reservas.calendar.disconnect.body")}
        confirmLabel={t("reservas.calendar.disconnect")}
        cancelLabel={t("common.cancel")}
        destructive
        error={error}
        onConfirm={async () => {
          if (!letting) return;
          setError(null);
          const message = await save(letting.id, null, t);
          if (message !== null) {
            setError(message);
            return;
          }
          toast.success(t("reservas.calendar.disconnected"));
          refresh();
          setLetting(null);
        }}
      />
    </>
  );
}

/** Saves and answers with what to tell the person, or `null` if it went well. */
async function save(id: string, calendarId: string | null, t: ReturnType<typeof useReservas>["t"]): Promise<string | null> {
  let res: SaveResult;
  try {
    res = await staffCalendarAction({ id, calendar_id: calendarId });
  } catch {
    return t("common.error.backend");
  }
  if (res.ok) return null;
  const ours = res.code ? SAVE_FAILURES[res.code] : undefined;
  if (ours) return t(ours);
  const f = failureMessage(res);
  return t(f.key as MessageKey, f.vars);
}

function PersonRow({
  member,
  calendars,
  canPick,
  onDisconnect,
}: {
  member: StaffMember;
  calendars: CalendarAccount["calendars"];
  canPick: boolean;
  onDisconnect: () => void;
}) {
  const { t, refresh } = useReservas();
  const nameId = React.useId();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const cal = member.calendar;
  const isLinked = cal.status !== "none";

  // Se guarda al confirmar, no al elegir: con el teclado, cada flecha cambia la selección, y
  // guardar mueve los eventos de esa persona a otro calendario.
  const [picked, setPicked] = React.useState("");

  async function choose(calendarId: string) {
    if (!calendarId) return;
    setBusy(true);
    setError(null);
    const message = await save(member.id, calendarId, t);
    setBusy(false);
    if (message !== null) {
      setError(message);
      return;
    }
    setPicked("");
    toast.success(t("reservas.calendar.saved"));
    refresh();
  }

  return (
    <li aria-labelledby={nameId} className="flex min-w-0 flex-wrap items-start gap-3 py-3">
      <Initials name={member.name} />
      <div className="flex min-w-0 flex-1 basis-40 flex-col gap-1">
        <span id={nameId} className="truncate text-sm font-medium" title={member.name}>
          {member.name}
        </span>
        <span className="truncate text-xs text-muted-foreground" title={cal.calendar_name ?? undefined}>
          {isLinked ? (cal.calendar_name ?? t("reservas.calendar.title")) : t("reservas.calendar.unlinked")}
        </span>
        <CalendarState calendar={cal} />
        {error ? (
          <p role="alert" className="text-xs text-pretty text-destructive">
            {error}
          </p>
        ) : null}
      </div>
      {canPick || isLinked ? (
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
          {canPick ? (
            <NativeSelect
              size="sm"
              aria-label={t("reservas.calendar.pick.aria", { name: member.name })}
              value={picked}
              disabled={busy}
              wrapperClassName="w-48"
              onChange={(e) => setPicked(e.target.value)}
            >
              <option value="">{isLinked ? t("reservas.calendar.pick.change") : t("reservas.calendar.pick")}</option>
              {calendars.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          ) : null}
          {canPick && picked ? (
            <Button size="xs" disabled={busy} loading={busy} onClick={() => void choose(picked)} aria-label={t("reservas.calendar.pick.save.aria", { name: member.name })}>
              {t("reservas.calendar.pick.save")}
            </Button>
          ) : null}
          {isLinked ? (
            <Button size="xs" variant="ghost" disabled={busy} aria-label={t("reservas.calendar.disconnect.aria", { name: member.name })} onClick={onDisconnect}>
              {t("reservas.calendar.disconnect")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function CalendarState({ calendar }: { calendar: StaffCalendar }) {
  const { t } = useReservas();
  const words = useWords();
  if (calendar.status === "none") return null;
  const when = calendar.last_sync_at ? words.instant(calendar.last_sync_at) : null;
  if (calendar.status === "connected") {
    return <p className="text-xs text-pretty text-muted-foreground">{when ? t("reservas.calendar.synced", { when }) : t("reservas.calendar.firstSync")}</p>;
  }
  const key: MessageKey =
    calendar.status === "needs_reauth" ? "reservas.calendar.state.reauth" : (STATE_OF_ERROR[calendar.last_error ?? ""] ?? "reservas.calendar.state.other");
  return (
    <>
      <p className="text-xs text-pretty text-destructive">{t(key)}</p>
      {when ? <p className="text-xs text-pretty text-muted-foreground">{t("reservas.calendar.lastSync", { when })}</p> : null}
    </>
  );
}
