"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Field, NativeSelect, Section, Switch } from "@nexus/ui";

import { patchSettingsAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { ReservasSettingsPatch } from "@/lib/backend/reservas";

import { useReservas } from "../context";
import { failureMessage } from "../model/vocab";
import { BusinessHoursDialog, HoursTable } from "./hours-editor";

/**
 * Settings saves (spec 043, T025): every PATCH carries the version it read
 * (`If-Match`). A 412 means someone changed the settings meanwhile: the
 * screen says so and shows what is there now instead of overwriting it.
 */
export function useSettingsPatch() {
  const { t, settings, refresh } = useReservas();
  const version = React.useRef(settings.version);
  React.useEffect(() => {
    version.current = settings.version;
  }, [settings.version]);
  const [busy, setBusy] = React.useState(false);
  const patch = React.useCallback(
    async (body: ReservasSettingsPatch): Promise<boolean> => {
      setBusy(true);
      try {
        const res = await patchSettingsAction({ version: version.current, patch: body });
        if (res.ok) {
          version.current = res.data.version;
          toast.success(t("reservas.settings.saved"));
          refresh();
          return true;
        }
        const f = failureMessage(res);
        toast.error(t(f.key as MessageKey, f.vars));
        if (res.status === 412) refresh();
        return false;
      } catch {
        toast.error(t("common.error.backend"));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [t, refresh],
  );
  return { patch, busy };
}

/** A setting that is on or off, saved as it is switched (spec 017, R5.4). */
export function SwitchRow({
  id,
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <div className="flex min-w-0 items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <label id={`${id}-label`} htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        {hint ? (
          <p id={`${id}-hint`} className="text-xs text-pretty text-muted-foreground">
            {hint}
          </p>
        ) : null}
      </div>
      <Switch
        id={id}
        checked={checked}
        disabled={disabled}
        aria-labelledby={`${id}-label`}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onCheckedChange={onChange}
      />
    </div>
  );
}

const LEADS = [60, 120, 240, 1440] as const;

export function WaitlistSettings() {
  const { t, settings, mode } = useReservas();
  const { patch, busy } = useSettingsPatch();
  return (
    <Section title={t("reservas.settings.waitlist.title")}>
      <SwitchRow
        id="reservas-waitlist"
        label={t("reservas.settings.waitlist.switch")}
        hint={t(mode === "services" ? "reservas.settings.waitlist.body.services" : "reservas.settings.waitlist.body.capacity")}
        checked={settings.waitlist.enabled}
        disabled={busy}
        onChange={(on) => void patch({ waitlist: { enabled: on } })}
      />
      <Field label={t("reservas.settings.lead")} hint={t("reservas.settings.lead.hint")}>
        {(a11y) => (
          <NativeSelect
            {...a11y}
            value={settings.waitlist.lead_minutes}
            disabled={busy}
            onChange={(e) => void patch({ waitlist: { lead_minutes: Number(e.target.value) } })}
            wrapperClassName="w-48"
          >
            {LEADS.map((m) => (
              <option key={m} value={m}>
                {t("reservas.settings.lead.option", { hours: m / 60 })}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
    </Section>
  );
}

export function BusinessHoursSection() {
  const { t, settings } = useReservas();
  const [editing, setEditing] = React.useState(false);
  return (
    <Section
      title={t("reservas.settings.hours.title")}
      description={t("reservas.settings.hours.body")}
      actions={
        <Button size="sm" variant="outline" aria-label={t("reservas.settings.hours.edit.aria")} onClick={() => setEditing(true)}>
          {t("reservas.settings.hours.edit")}
        </Button>
      }
    >
      {settings.hours_missing ? <Callout tone="warning">{t("reservas.settings.hours.missing")}</Callout> : <HoursTable value={settings.business_hours} />}
      {editing ? <BusinessHoursDialog onClose={() => setEditing(false)} /> : null}
    </Section>
  );
}
