"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, NativeSelect, Switch } from "@nexus/ui";

import { putBusinessHoursAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import { WEEKDAYS, type TimeRange, type WeekHours, type Weekday } from "@/lib/backend/reservas";

import { useReservas } from "../context";
import { dayValid, rangesLabel, timeOptions, weekInvalidDays } from "../model/hours";
import { failureMessage } from "../model/vocab";

const OPTIONS = timeOptions();

function TimeSelect({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const options = OPTIONS.includes(value) ? OPTIONS : [...OPTIONS, value].sort();
  return (
    <NativeSelect size="sm" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} wrapperClassName="w-24">
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </NativeSelect>
  );
}

/**
 * A week of hours (spec 043, T025): a switch per day, from–to, and an
 * optional second range — the lunch break is the gap between them. Used for
 * the business and for a person of the team.
 */
export function HoursEditor({ value, onChange }: { value: WeekHours; onChange: (next: WeekHours) => void }) {
  const { t } = useReservas();
  const set = (day: Weekday, ranges: TimeRange[]) => onChange({ ...value, [day]: ranges });
  return (
    <ul className="flex min-w-0 flex-col divide-y divide-border">
      {WEEKDAYS.map((day) => {
        const ranges = value[day];
        const name = t(`reservas.weekday.${day}` as MessageKey);
        const open = ranges.length > 0;
        const ok = dayValid(ranges);
        return (
          <li key={day} className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 py-2">
            <span className="flex w-36 shrink-0 items-center gap-3">
              <Switch
                checked={open}
                aria-label={t("reservas.hours.open", { day: name })}
                onCheckedChange={(on) => set(day, on ? [{ from: "09:00", to: "19:00" }] : [])}
              />
              <span className="text-sm">{name}</span>
            </span>
            {open ? (
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                {ranges.map((r, i) => (
                  <span key={i} className="inline-flex items-center gap-1" role="group" aria-label={t("reservas.hours.range", { day: name, n: i + 1 })}>
                    <TimeSelect label={t("reservas.hours.from")} value={r.from} onChange={(v) => set(day, ranges.map((x, j) => (j === i ? { ...x, from: v } : x)))} />
                    <span aria-hidden="true">–</span>
                    <TimeSelect label={t("reservas.hours.to")} value={r.to} onChange={(v) => set(day, ranges.map((x, j) => (j === i ? { ...x, to: v } : x)))} />
                    {i === 1 ? (
                      <Button type="button" size="icon-sm" variant="ghost" aria-label={t("reservas.hours.removeRange", { day: name })} onClick={() => set(day, [ranges[0]!])}>
                        <X aria-hidden="true" />
                      </Button>
                    ) : null}
                  </span>
                ))}
                {ranges.length === 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => set(day, [ranges[0]!, { from: ranges[0]!.to < "22:00" ? ranges[0]!.to : "20:00", to: "23:00" }])}
                  >
                    <Plus aria-hidden="true" />
                    {t("reservas.hours.addRange")}
                  </Button>
                ) : null}
              </span>
            ) : (
              <span className="text-sm text-muted-foreground">{t("reservas.settings.hours.closed")}</span>
            )}
            {!ok ? (
              <p role="alert" className="basis-full text-xs text-destructive">
                {t("reservas.hours.invalid", { day: name })}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

/** The week as a table to read: «Lunes · 09:00 – 14:00 · 15:00 – 19:00» or «Cerrado». */
export function HoursTable({ value }: { value: WeekHours }) {
  const { t } = useReservas();
  return (
    <dl className="grid min-w-0 grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
      {WEEKDAYS.map((day) => (
        <React.Fragment key={day}>
          <dt className="text-muted-foreground">{t(`reservas.weekday.${day}` as MessageKey)}</dt>
          <dd className="tabular-nums">{rangesLabel(value[day]) ?? t("reservas.settings.hours.closed")}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

/** «Horario del negocio» edit dialog: saved in the business profile (PUT business-hours). */
export function BusinessHoursDialog({ onClose }: { onClose: () => void }) {
  const { t, settings, refresh } = useReservas();
  const [week, setWeek] = React.useState<WeekHours>(settings.business_hours);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const invalid = weekInvalidDays(week).length > 0;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await putBusinessHoursAction({ hours: week });
      if (res.ok) {
        toast.success(t("reservas.hours.saved"));
        refresh();
        onClose();
        return;
      }
      const f = failureMessage(res);
      setError(t(f.key as MessageKey, f.vars));
    } catch {
      setError(t("common.error.backend"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("reservas.settings.hours.title")}</DialogTitle>
          <DialogDescription>{t("reservas.hours.dialog.body")}</DialogDescription>
        </DialogHeader>
        <HoursEditor value={week} onChange={setWeek} />
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void save()} loading={busy} disabled={invalid}>
            {t("reservas.settings.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
