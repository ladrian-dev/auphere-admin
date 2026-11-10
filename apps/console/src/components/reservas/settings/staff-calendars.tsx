"use client";

import { MoreHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  Label,
  Section,
  Skeleton,
} from "@nexus/ui";

import {
  connectStaffCalendarAction,
  refreshStaffCalendarAction,
  staffCalendarAction,
  staffCalendarsAction,
} from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { StaffCalendar, StaffCalendarOption, StaffMember } from "@/lib/backend/reservas";

import { useReservas, useWords } from "../context";
import { failureMessage } from "../model/vocab";
import { Initials } from "../shared";

type T = ReturnType<typeof useReservas>["t"];
type Failure = { status: number; code?: string | null; info?: Record<string, unknown> };

/** `last_error` is a code of ours; one this screen doesn't know yet gets the general sentence. */
const STATE_OF_ERROR: Record<string, MessageKey> = {
  read: "reservas.calendar.state.read",
  write: "reservas.calendar.state.write",
  calendar_gone: "reservas.calendar.state.gone",
  new_account_refused: "reservas.calendar.state.newAccountRefused",
};

const FAILURES: Record<string, MessageKey> = {
  unknown_calendar: "reservas.calendar.fail.unknown",
  calendar_not_connected: "reservas.calendar.fail.notConnected",
  calendar_unavailable: "reservas.calendar.fail.unavailable",
  calendar_disconnecting: "reservas.calendar.fail.disconnecting",
  calendar_already_connected: "reservas.calendar.fail.alreadyConnected",
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function failure(res: Failure, t: T): string {
  if (res.code === "calendar_in_use") {
    return t("reservas.calendar.fail.inUse", { name: String(res.info?.used_by ?? "") });
  }
  const ours = res.code ? FAILURES[res.code] : undefined;
  if (ours) return t(ours);
  const f = failureMessage(res);
  return t(f.key as MessageKey, f.vars);
}

/** The one thing that resolves each state (spec 043, R12.1): everything else is in the menu. */
type Primary = "connect" | "reconnect" | "otherAccount" | "check" | "retry" | "choose" | null;

function primaryOf(cal: StaffCalendar): Primary {
  switch (cal.status) {
    case "none":
      return "connect";
    case "pending":
      return "check";
    case "needs_reauth":
      return "reconnect";
    case "needs_calendar":
      return cal.last_error === "no_calendar" ? "otherAccount" : "choose";
    case "error":
      if (cal.last_error === "new_account_refused") return "otherAccount";
      return cal.last_error === "calendar_gone" ? "choose" : "retry";
    default:
      return null;
  }
}

type Opening = { member: StaffMember; kind: "connect" | "choose" | "disconnect" };
type LoadedCalendars = { ok: true; data: { calendars: StaffCalendarOption[] } } | ({ ok: false } & Failure);

/**
 * Spec 043, requirement 12: each professional connects their own Google account from here.
 * Reservas is what counts (R11): this only says what comes in and what goes out.
 *
 * One row per person, one main action per state and the rest in a menu. A state nobody can
 * resolve from this row is a bug: there is nobody else to ask.
 */
export function StaffCalendarsSection() {
  const { t, data, refresh } = useReservas();
  const [opening, setOpening] = React.useState<Opening | null>(null);
  useReturnFromGoogle();
  const staff = data.staff;
  return (
    <Section title={t("reservas.calendar.title")} description={t("reservas.calendar.body")}>
      {staff === null ? (
        <Callout
          tone="danger"
          action={
            <Button size="xs" variant="outline" onClick={() => refresh()}>
              {t("common.retry")}
            </Button>
          }
        >
          {t("reservas.calendar.loadError")}
        </Callout>
      ) : staff.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.calendar.noTeam")}</p>
      ) : (
        <ul className="flex min-w-0 flex-col divide-y divide-border">
          {staff.map((s) => (
            <PersonRow key={s.id} member={s} onOpen={(kind) => setOpening({ member: s, kind })} />
          ))}
        </ul>
      )}
      {opening?.kind === "connect" ? <ConnectDialog member={opening.member} onClose={() => setOpening(null)} /> : null}
      {opening?.kind === "choose" ? <ChooseDialog member={opening.member} onClose={() => setOpening(null)} /> : null}
      <DisconnectDialog member={opening?.kind === "disconnect" ? opening.member : null} onClose={() => setOpening(null)} />
    </Section>
  );
}

/**
 * Coming back from Google: `?calendar_return={id}`. It looks at how that person ended up
 * without waiting for the next pass, says it once, and takes what the provider added off the
 * address so a reload doesn't say it again.
 */
function useReturnFromGoogle() {
  const { t, data, refresh } = useReservas();
  const router = useRouter();
  const done = React.useRef(false);
  React.useEffect(() => {
    if (done.current) return;
    done.current = true;
    const here = new URL(window.location.href);
    const id = here.searchParams.get("calendar_return");
    if (!id) return;
    for (const key of ["calendar_return", "status", "connectedAccountId", "connected_account_id", "appName"]) here.searchParams.delete(key);
    // By the router: a refresh would bring back what ``history`` alone took off the address.
    router.replace(`${here.pathname}${here.search}`, { scroll: false });
    if (!UUID_RE.test(id)) return;
    const name = data.staff?.find((s) => s.id === id)?.name ?? "";
    void refreshStaffCalendarAction({ id })
      .then((res) => {
        const status = res.ok ? res.data.calendar.status : null;
        if (status === "connected") toast.success(t("reservas.calendar.back.connected", { name }));
        else if (status === "needs_calendar") toast.success(t("reservas.calendar.back.choose", { name }));
        else if (status === "pending") toast.success(t("reservas.calendar.back.pending", { name }));
        else toast.error(t("reservas.calendar.back.failed", { name }));
        refresh();
      })
      .catch(() => toast.error(t("reservas.calendar.back.failed", { name })));
    // Once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

function PersonRow({ member, onOpen }: { member: StaffMember; onOpen: (kind: Opening["kind"]) => void }) {
  const { t, refresh } = useReservas();
  const nameId = React.useId();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const cal = member.calendar;
  const name = member.name;

  async function look() {
    setBusy(true);
    setError(null);
    try {
      const res = await refreshStaffCalendarAction({ id: member.id });
      if (!res.ok) {
        setError(failure(res, t));
      } else if (res.data.calendar.status === "connected") {
        toast.success(t(primaryOf(cal) === "retry" ? "reservas.calendar.synced.again" : "reservas.calendar.back.connected", { name }));
      } else if (res.data.calendar.status === "pending") {
        setError(t("reservas.calendar.stillPending"));
      } else if (res.data.calendar.status === "error") {
        setError(t("reservas.calendar.stillFailing"));
      }
    } catch {
      setError(t("common.error.backend"));
    } finally {
      setBusy(false);
    }
    refresh();
  }

  const primary = primaryOf(cal);
  return (
    <li aria-labelledby={nameId} className="flex min-w-0 flex-wrap items-start gap-3 py-3">
      <Initials name={name} />
      <div className="flex min-w-0 flex-1 basis-40 flex-col gap-1">
        <span id={nameId} className="truncate text-sm font-medium" title={name}>
          {name}
        </span>
        <CalendarState calendar={cal} />
        {error ? (
          <p role="alert" className="text-xs text-pretty text-destructive">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {primary === "check" || primary === "retry" ? (
          <Button
            size="xs"
            variant="outline"
            loading={busy}
            disabled={busy}
            aria-label={t(primary === "check" ? "reservas.calendar.check.aria" : "reservas.calendar.retry.aria", { name })}
            onClick={() => void look()}
          >
            {t(primary === "check" ? "reservas.calendar.check" : "common.retry")}
          </Button>
        ) : primary === "choose" ? (
          <Button size="xs" variant="outline" aria-label={t("reservas.calendar.choose.aria", { name })} onClick={() => onOpen("choose")}>
            {t("reservas.calendar.choose")}
          </Button>
        ) : primary !== null ? (
          <Button
            size="xs"
            variant="outline"
            aria-label={t(
              primary === "connect"
                ? "reservas.calendar.connect.aria"
                : primary === "reconnect"
                  ? "reservas.calendar.reconnect.aria"
                  : "reservas.calendar.otherAccount.aria",
              { name },
            )}
            onClick={() => onOpen("connect")}
          >
            {t(primary === "connect" ? "reservas.calendar.connect" : primary === "reconnect" ? "reservas.calendar.reconnect" : "reservas.calendar.otherAccount")}
          </Button>
        ) : null}
        {cal.status !== "none" ? <PersonMenu member={member} primary={primary} onOpen={onOpen} /> : null}
      </div>
    </li>
  );
}

function PersonMenu({ member, primary, onOpen }: { member: StaffMember; primary: Primary; onOpen: (kind: Opening["kind"]) => void }) {
  const { t } = useReservas();
  const status = member.calendar.status;
  const canChoose = (status === "connected" || status === "error") && primary !== "choose";
  const canConnect = (status === "pending" || status === "error" || status === "needs_calendar") && primary !== "otherAccount";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t("reservas.calendar.menu.aria", { name: member.name })}
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
      >
        <MoreHorizontal aria-hidden="true" className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {canChoose ? <DropdownMenuItem onClick={() => onOpen("choose")}>{t("reservas.calendar.change")}</DropdownMenuItem> : null}
        {canConnect ? (
          <DropdownMenuItem onClick={() => onOpen("connect")}>
            {t(status === "pending" ? "reservas.calendar.linkAgain" : "reservas.calendar.otherAccount")}
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onClick={() => onOpen("disconnect")}>{t("reservas.calendar.disconnect")}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Says what's going to happen before leaving for Google, and which account it has to be. */
function ConnectDialog({ member, onClose }: { member: StaffMember; onClose: () => void }) {
  const { t, refresh } = useReservas();
  const name = member.name;
  const [busy, setBusy] = React.useState<"go" | "copy" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [link, setLink] = React.useState<string | null>(null);

  async function ask(share: boolean): Promise<string | null> {
    setError(null);
    try {
      const res = await connectStaffCalendarAction({ id: member.id, share });
      if (res.ok) return res.data.redirect_url;
      setError(failure(res, t));
    } catch {
      setError(t("common.error.backend"));
    }
    return null;
  }

  async function go() {
    setBusy("go");
    const url = await ask(false);
    if (url) {
      window.location.assign(url);
      return;
    }
    setBusy(null);
  }

  async function copy() {
    setBusy("copy");
    // Otro enlace dejaría sin valor el que ya está a la vista.
    const url = link ?? (await ask(true));
    setBusy(null);
    if (!url) return;
    refresh();
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // Without the clipboard, the link itself: never say it was copied when it wasn't.
      setLink(url);
      return;
    }
    toast.success(t("reservas.calendar.linkCopied", { name }));
    onClose();
  }

  return (
    <Dialog open onOpenChange={(o) => (o ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("reservas.calendar.connect.title", { name })}</DialogTitle>
          <DialogDescription>{t("reservas.calendar.connect.lead", { name })}</DialogDescription>
        </DialogHeader>
        <ul className="flex min-w-0 list-disc flex-col gap-1 pl-5 text-sm text-pretty">
          <li>{t("reservas.calendar.connect.reads")}</li>
          <li>{t("reservas.calendar.connect.writes")}</li>
          <li>{t("reservas.calendar.connect.rules")}</li>
        </ul>
        <p className="text-sm text-pretty text-muted-foreground">{t("reservas.calendar.connect.notHere", { name })}</p>
        {link ? (
          <div className="flex min-w-0 flex-col gap-1">
            <Label htmlFor={`calendar-link-${member.id}`}>{t("reservas.calendar.linkLabel", { name })}</Label>
            <Input id={`calendar-link-${member.id}`} readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
          </div>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-pretty text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" disabled={busy !== null} loading={busy === "copy"} onClick={() => void copy()}>
            {t("reservas.calendar.copyLink")}
          </Button>
          <Button disabled={busy !== null} loading={busy === "go"} onClick={() => void go()}>
            {t("reservas.calendar.goToGoogle")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChooseDialog({ member, onClose }: { member: StaffMember; onClose: () => void }) {
  const { t, refresh } = useReservas();
  const [attempt, setAttempt] = React.useState(0);
  // Its own read and not `useActionLoad`: the refusal has to say why. «It's no longer connected»
  // is not «Google isn't answering», and only one of them is worth trying again.
  const [loaded, setLoaded] = React.useState<{ attempt: number; res: LoadedCalendars } | null>(null);
  React.useEffect(() => {
    let live = true;
    staffCalendarsAction({ id: member.id })
      .then((res) => {
        if (live) setLoaded({ attempt, res });
      })
      .catch(() => {
        if (live) setLoaded({ attempt, res: { ok: false, status: 0, code: "calendar_unavailable" } });
      });
    return () => {
      live = false;
    };
  }, [member.id, attempt]);
  const answer = loaded?.attempt === attempt ? loaded.res : null;
  const [picked, setPicked] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const options: StaffCalendarOption[] | null = answer?.ok ? answer.data.calendars : null;

  async function save() {
    if (!picked) return;
    setBusy(true);
    setError(null);
    try {
      const res = await staffCalendarAction({ id: member.id, calendar_id: picked });
      if (res.ok) {
        toast.success(t("reservas.calendar.saved"));
        refresh();
        onClose();
        return;
      }
      setError(failure(res, t));
    } catch {
      setError(t("common.error.backend"));
    }
    setBusy(false);
  }

  return (
    <Dialog open onOpenChange={(o) => (o ? undefined : onClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("reservas.calendar.choose.title", { name: member.name })}</DialogTitle>
          <DialogDescription>{t("reservas.calendar.choose.lead")}</DialogDescription>
        </DialogHeader>
        {answer !== null && !answer.ok ? (
          <Callout
            tone="danger"
            action={
              answer.code === "calendar_not_connected" ? undefined : (
                <Button size="xs" variant="outline" onClick={() => setAttempt((n) => n + 1)}>
                  {t("common.retry")}
                </Button>
              )
            }
          >
            {failure(answer, t)}
          </Callout>
        ) : options === null ? (
          <div role="status" aria-label={t("reservas.calendar.loading")} className="flex min-w-0 flex-col gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : options.length === 0 ? (
          <p className="text-sm text-pretty text-muted-foreground">{t("reservas.calendar.noCalendars")}</p>
        ) : (
          <fieldset className="flex min-w-0 flex-col gap-1">
            <legend className="sr-only">{t("reservas.calendar.choose.title", { name: member.name })}</legend>
            {options.map((c) => (
              <label
                key={c.id}
                className="flex min-h-10 min-w-0 items-center gap-2 rounded-sm px-2 py-1 text-sm has-[:disabled]:text-muted-foreground has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"
              >
                <input
                  type="radio"
                  name={`calendar-${member.id}`}
                  value={c.id}
                  disabled={c.used_by !== null || busy}
                  checked={picked === c.id}
                  onChange={() => setPicked(c.id)}
                  className="size-4 shrink-0 accent-primary"
                />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate" title={c.name}>
                    {c.name}
                  </span>
                  {c.used_by !== null ? <span className="truncate text-xs">{t("reservas.calendar.usedBy", { name: c.used_by })}</span> : null}
                </span>
              </label>
            ))}
          </fieldset>
        )}
        {error ? (
          <p role="alert" className="text-sm text-pretty text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          {options !== null && options.length > 0 ? (
            <Button disabled={!picked || busy} loading={busy} onClick={() => void save()}>
              {t("common.save")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DisconnectDialog({ member, onClose }: { member: StaffMember | null; onClose: () => void }) {
  const { t, refresh } = useReservas();
  const [error, setError] = React.useState<string | null>(null);
  return (
    <ConfirmDialog
      open={member !== null}
      onOpenChange={(o) => {
        if (!o) {
          setError(null);
          onClose();
        }
      }}
      title={member ? t("reservas.calendar.disconnect.title", { name: member.name }) : ""}
      description={t("reservas.calendar.disconnect.body")}
      confirmLabel={t("reservas.calendar.disconnect")}
      cancelLabel={t("common.cancel")}
      destructive
      error={error}
      onConfirm={async () => {
        if (!member) return;
        setError(null);
        try {
          const res = await staffCalendarAction({ id: member.id, calendar_id: null });
          if (!res.ok) {
            setError(failure(res, t));
            return;
          }
        } catch {
          setError(t("common.error.backend"));
          return;
        }
        toast.success(t("reservas.calendar.disconnected"));
        refresh();
        onClose();
      }}
    />
  );
}

/** What the row says: which account and calendar, how the last pass went, and what it means for the slots. */
function CalendarState({ calendar }: { calendar: StaffCalendar }) {
  const { t } = useReservas();
  return (
    <>
      <OwnCalendarState calendar={calendar} />
      {calendar.business_busy ? (
        <p className="text-xs text-pretty text-muted-foreground">{t("reservas.calendar.businessBusy")}</p>
      ) : null}
    </>
  );
}

function OwnCalendarState({ calendar }: { calendar: StaffCalendar }) {
  const { t } = useReservas();
  const words = useWords();
  const when = calendar.last_sync_at ? words.instant(calendar.last_sync_at) : null;
  const account = calendar.account ?? null;
  const name = calendar.calendar_name ?? null;
  const which = account && name && name !== account ? `${account} · ${name}` : (account ?? name);
  const line = which ? (
    <span className="truncate text-xs text-muted-foreground" title={which}>
      {which}
    </span>
  ) : null;
  switch (calendar.status) {
    case "none":
      return <span className="text-xs text-muted-foreground">{t("reservas.calendar.state.none")}</span>;
    case "pending":
      return (
        <>
          {line}
          <p className="text-xs text-pretty text-muted-foreground">{t("reservas.calendar.state.pending")}</p>
        </>
      );
    case "connected":
      return (
        <>
          {line}
          <p className="text-xs text-pretty text-muted-foreground">{when ? t("reservas.calendar.synced", { when }) : t("reservas.calendar.firstSync")}</p>
        </>
      );
    case "needs_calendar":
      return (
        <>
          {line}
          <p className="text-xs text-pretty text-warning">
            {t(
              calendar.last_error === "calendar_in_use"
                ? "reservas.calendar.state.inUse"
                : calendar.last_error === "no_calendar"
                  ? "reservas.calendar.state.noCalendar"
                  : "reservas.calendar.state.choose",
            )}
          </p>
        </>
      );
    default: {
      const key: MessageKey =
        calendar.status === "needs_reauth" ? "reservas.calendar.state.reauth" : (STATE_OF_ERROR[calendar.last_error ?? ""] ?? "reservas.calendar.state.other");
      return (
        <>
          {line}
          <p className="text-xs text-pretty text-destructive">{t(key)}</p>
          {when ? <p className="text-xs text-pretty text-muted-foreground">{t("reservas.calendar.lastSync", { when })}</p> : null}
        </>
      );
    }
  }
}
