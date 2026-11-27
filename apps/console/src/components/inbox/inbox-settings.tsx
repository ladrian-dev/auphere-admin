"use client";

import { Settings } from "lucide-react";
import * as React from "react";

import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Label,
  NativeSelect,
  Skeleton,
  Switch,
} from "@nexus/ui";

import { inboxSettingsAction, patchInboxSettingsAction } from "@/app/(console)/inbox/actions";
import { SOUND_EVENT, setSoundOn, soundOn } from "@/components/live/chime";
import { useActionLoad } from "@/components/reservas/model/use-load";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

import { INBOX_AUTOCLOSE_HOURS, type InboxAutoclose } from "./inbox-model";

const TERM_LABEL: Record<InboxAutoclose, MessageKey> = {
  24: "inbox.settings.autoclose.24",
  72: "inbox.settings.autoclose.72",
  168: "inbox.settings.autoclose.168",
  720: "inbox.settings.autoclose.720",
};

/**
 * The Inbox's settings (spec 064, requisito 5.1): one value — after how long
 * without messages a conversation the agent answers is resolved on its own.
 * «Nunca» is where it starts. It is read when the dialog opens, each time, and
 * saved as it is chosen. A save that fails is said and the field stays on what
 * is stored. Loading and a failed read have no field to touch.
 */
export function InboxSettings() {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  // Each opening, and each «Reintentar», is a new read.
  const [read, setRead] = React.useState(0);
  const load = useActionLoad(open ? `inbox-settings|${read}` : null, () => inboxSettingsAction());
  const [stored, setStored] = React.useState<{ read: number; hours: number | null } | null>(null);
  const [outcome, setOutcome] = React.useState<{ read: number; kind: "saved" | "failed" } | null>(null);
  const [pending, setPending] = React.useState<{ read: number; hours: InboxAutoclose | null } | null>(null);
  const busy = pending !== null;

  // What is being saved shows at once; a refusal puts back what is stored.
  const hours =
    pending?.read === read
      ? pending.hours
      : stored?.read === read
        ? stored.hours
        : load.kind === "ok"
          ? load.data.autoclose_hours
          : null;
  const said = outcome?.read === read ? outcome.kind : null;

  function change(next: boolean) {
    if (next) setRead((r) => r + 1);
    setOpen(next);
  }

  async function save(next: InboxAutoclose | null) {
    if (busy) return;
    setPending({ read, hours: next });
    setOutcome(null);
    try {
      const res = await patchInboxSettingsAction({ autoclose_hours: next });
      if (res.ok) {
        setStored({ read, hours: res.data.autoclose_hours });
        setOutcome({ read, kind: "saved" });
      } else {
        setOutcome({ read, kind: "failed" });
      }
    } catch {
      setOutcome({ read, kind: "failed" });
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={t("inbox.settings.title")} title={t("inbox.settings.title")} onClick={() => change(true)}>
        <Settings className="size-4" aria-hidden="true" />
      </Button>
      <Dialog open={open} onOpenChange={change}>
        <DialogContent data-slot="inbox-settings">
          <DialogHeader>
            <DialogTitle>{t("inbox.settings.title")}</DialogTitle>
            <DialogDescription>{t("inbox.settings.body")}</DialogDescription>
          </DialogHeader>
          {load.kind === "ok" ? (
            <Field label={t("inbox.settings.autoclose")} hint={t("inbox.settings.autoclose.hint")}>
              {(a11y) => (
                <NativeSelect
                  {...a11y}
                  value={hours ?? ""}
                  // Not `disabled`: it would drop the focus of the select it is on.
                  aria-disabled={busy || undefined}
                  onChange={(e) => void save(e.target.value === "" ? null : (Number(e.target.value) as InboxAutoclose))}
                  wrapperClassName="w-56"
                >
                  <option value="">{t("inbox.settings.autoclose.never")}</option>
                  {INBOX_AUTOCLOSE_HOURS.map((h) => (
                    <option key={h} value={h}>
                      {t(TERM_LABEL[h])}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
          ) : load.kind === "error" ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription className="flex flex-wrap items-center gap-2">
                {t("inbox.settings.error")}
                <Button type="button" size="xs" variant="outline" onClick={() => setRead((r) => r + 1)}>
                  {t("common.retry")}
                </Button>
              </AlertDescription>
            </Alert>
          ) : (
            // The field's own measures, so nothing jumps when it arrives.
            <div role="status" aria-label={t("inbox.settings.loading")} className="flex flex-col gap-2">
              <Skeleton className="h-5 w-64" />
              <Skeleton className="h-9 w-56" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          )}
          <SoundSwitch />
          {/* Always mounted, so a screen reader hears the text when it changes (WCAG 4.1.3). */}
          <p role="status" className="min-h-5 text-sm text-muted-foreground">
            {said === "saved" ? t("inbox.settings.saved") : ""}
          </p>
          {said === "failed" ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{t("inbox.settings.saveError")}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => change(false)}>
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Spec 082 (R3.4): the sound when a message arrives, on or off **in this
 * browser** — a preference of the work station, saved at once, no API. On by
 * default. It does not wait for the server read: it is always there.
 */
function SoundSwitch() {
  const t = useT();
  const id = React.useId();
  const [on, setOn] = React.useState(true);
  React.useEffect(() => {
    // Read after mount: the server cannot know what this browser chose.
    const sync = () => setOn(soundOn());
    sync();
    window.addEventListener(SOUND_EVENT, sync);
    return () => window.removeEventListener(SOUND_EVENT, sync);
  }, []);
  return (
    <div className="flex min-w-0 items-start gap-3" data-slot="inbox-sound">
      <Switch
        id={`${id}-sound`}
        checked={on}
        onCheckedChange={(v) => setSoundOn(v === true)}
        aria-describedby={`${id}-sound-hint`}
        className="mt-1"
      />
      <div className="grid min-w-0 flex-1 gap-1">
        <Label htmlFor={`${id}-sound`} className="text-sm font-medium">
          {t("inbox.settings.sound")}
        </Label>
        <p id={`${id}-sound-hint`} className="text-sm text-pretty text-muted-foreground">
          {t("inbox.settings.sound.hint")}
        </p>
      </div>
    </div>
  );
}
