"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, NativeSelect, StatusBadge, Switch } from "@nexus/ui";

import { patchBusinessHoursAction } from "@/app/(console)/reservas/actions";
import { blockRows, draftFromHours, shiftsText, validateDraft, type HoursDraft } from "@/components/business/sections/hours-model";
import { WeekEditor } from "@/components/business/sections/week-editor";
import { useDiscardGuard } from "@/components/use-discard-guard";
import type { MessageKey } from "@/i18n/messages";
import { DAYS, type Day } from "@/lib/backend/business-sections";
import { WEEKDAYS, type LocationHours, type TimeRange, type WeekHours, type Weekday } from "@/lib/backend/reservas";

import { useReservas } from "../context";
import { changedDays, dayValid, hoursPatch, reviewDays, timeOptions } from "../model/hours";
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

/** Reservas names the days by their full name (`reservas.weekday.*`); the ficha's keys are short. */
const WEEKDAY_OF: Record<Day, Weekday> = {
  mon: "monday",
  tue: "tuesday",
  wed: "wednesday",
  thu: "thursday",
  fri: "friday",
  sat: "saturday",
  sun: "sunday",
};

/**
 * The business's week to read (spec 056, 5.1), from the ficha's shape: night
 * shifts say «(día siguiente)», 24:00 closes, and a stored time off the 5-minute
 * step says «Revísalo» (5.5).
 */
export function HoursTable() {
  const { t, settings } = useReservas();
  const review = reviewDays(settings.hours);
  return (
    <dl className="grid min-w-0 grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
      {DAYS.map((day) => {
        const shifts = settings.hours.days[day] ?? [];
        return (
          <React.Fragment key={day}>
            <dt className="text-muted-foreground">{t(`reservas.weekday.${WEEKDAY_OF[day]}` as MessageKey)}</dt>
            <dd className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="tabular-nums">{shifts.length ? shiftsText(shifts, t("business.hours.read.next_day")) : t("reservas.settings.hours.closed")}</span>
              {review.includes(day) ? (
                <StatusBadge tone="warning" title={t("business.hours.review.hint")}>
                  {t("business.hours.review")}
                </StatusBadge>
              ) : null}
            </dd>
          </React.Fragment>
        );
      })}
    </dl>
  );
}

/** Each location's hours, to read (5.1): its own ones are changed in the ficha, not here. */
export function LocationHoursNote({ locations }: { locations: readonly LocationHours[] }) {
  const { t } = useReservas();
  if (!locations.length) return null;
  return (
    <div className="grid min-w-0 gap-1 text-sm">
      <ul className="grid min-w-0 gap-1">
        {locations.map((l) => (
          <li key={l.location.id} className="text-pretty break-words">
            {l.has_own_hours
              ? t("reservas.hours.location.own", { name: l.location.name, label: l.label ?? "" })
              : t("reservas.hours.location.business", { name: l.location.name })}
          </li>
        ))}
      </ul>
      <p className="text-xs text-pretty text-muted-foreground">{t("reservas.hours.locations.hint")}</p>
    </div>
  );
}

const HOURS_ERRORS = new Set(["too_many_shifts", "overlap", "overlap_next_day", "invalid_time", "bad_step", "invalid_day"]);

/**
 * «Horario del negocio» (spec 056, requisito 5): the ficha's editor, day by day,
 * with its rules. Only the days that changed travel, with the revision that was
 * read (`PATCH business-hours`); what is stored and was not touched — a night
 * shift, a sixth shift, a time off the step — stays as it is. Closing with
 * changes asks first (12.3).
 */
export function BusinessHoursDialog({ onClose }: { onClose: () => void }) {
  const { t, settings, refresh } = useReservas();
  const original = settings.hours;
  const [draft, setDraft] = React.useState<HoursDraft>(() => ({ ...draftFromHours(original), layout: "daily" }));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const changed = changedDays(original, draft);
  const problems = validateDraft(draft, original);
  const guard = useDiscardGuard(changed.length > 0, onClose);
  const dayName = (d: string) => (DAYS.includes(d as Day) ? t(`business.hours.day.${d}` as MessageKey) : d);
  const problemText = (code: string, day: string) => t(`business.hours.error.${code}` as MessageKey, { day: dayName(day) });

  function change(next: HoursDraft) {
    setDraft(next);
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const res = await patchBusinessHoursAction(hoursPatch(original, draft));
      if (res.ok) {
        toast.success(t("reservas.hours.saved"));
        refresh();
        onClose();
        return;
      }
      if (res.status === 409) {
        setError(t("reservas.error.stale"));
        refresh();
      } else if (res.status === 422 && res.code && HOURS_ERRORS.has(res.code)) {
        setError(problemText(res.code, String(res.info?.day ?? "")));
      } else {
        const f = failureMessage(res);
        setError(t(f.key as MessageKey, f.vars));
      }
    } catch {
      setError(t("common.error.backend"));
    } finally {
      setBusy(false);
    }
  }

  const first = problems[0];
  return (
    <>
      <Dialog open onOpenChange={guard.onOpenChange}>
        <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{t("reservas.settings.hours.title")}</DialogTitle>
            <DialogDescription>{t("reservas.hours.dialog.body")}</DialogDescription>
          </DialogHeader>
          <WeekEditor draft={draft} rows={blockRows("daily")} editable review={reviewDays(original)} onChange={change} />
          <LocationHoursNote locations={settings.location_hours} />
          {first && !error ? (
            <p role="alert" className="text-sm text-destructive">
              {problemText(first.code, first.day)}
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={guard.close}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void save()} loading={busy} disabled={changed.length === 0 || problems.length > 0}>
              {t("reservas.settings.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {guard.dialog}
    </>
  );
}
