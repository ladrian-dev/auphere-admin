"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Input, NativeSelect } from "@nexus/ui";

import { createBlockAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";

import { useReservas, useWords } from "../context";
import { openDays, weekdayOf } from "../model/dates";
import { useIdempotencyKey } from "../model/idempotency";
import { scheduleTimes } from "../model/occupancy";
import { failureMessage } from "../model/vocab";
import { Chip, ChipGroup } from "../shared";

/**
 * «Bloquear horas» of Aforo (spec 043, T024): a day, a quick choice (a whole
 * shift or the whole day) or from–until as arrival times (the last one
 * included), and a reason that cannot be empty. What was already booked
 * stays: the toast says how many.
 */
export function BlockDialog({ prefill, onClose }: { prefill: { date?: string; from?: string; until?: string }; onClose: () => void }) {
  const { t, settings, today, refresh } = useReservas();
  const words = useWords();
  const key = useIdempotencyKey();
  const slots = scheduleTimes(settings.capacity?.schedule);
  const times = slots.map((s) => s.time);
  const shifts = settings.capacity?.schedule.model === "shifts" ? settings.capacity.schedule.shifts : [];
  const isOpen = (d: string) => settings.business_hours[weekdayOf(d)].length > 0;
  const [date, setDate] = React.useState(prefill.date && prefill.date >= today ? prefill.date : today);
  const days = openDays(today, 10, isOpen, date);
  const [from, setFrom] = React.useState(prefill.from && times.includes(prefill.from) ? prefill.from : (times[0] ?? ""));
  const [until, setUntil] = React.useState(prefill.until && times.includes(prefill.until) ? prefill.until : (times[times.length - 1] ?? ""));
  const [label, setLabel] = React.useState(t("reservas.block.label.default"));
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const dayOpen = isOpen(date) && times.length > 0;
  const ready = dayOpen && !!label.trim() && from <= until;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!ready) return;
    setBusy(true);
    const payload = { date, from, until, label: label.trim() };
    try {
      const res = await createBlockAction({ ...payload, idempotencyKey: key.take(payload) });
      if (res.ok) {
        key.done();
        toast.success(
          res.data.overlapping_bookings > 0
            ? t("reservas.block.done.overlap", { count: res.data.overlapping_bookings })
            : t("reservas.block.done"),
        );
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
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-md">
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{t("reservas.block.title")}</DialogTitle>
            <DialogDescription>{t("reservas.block.body")}</DialogDescription>
          </DialogHeader>
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">{t("reservas.form.day")}</legend>
            <ChipGroup label={t("reservas.form.day")}>
              {days.map((d) => (
                <Chip key={d} pressed={d === date} onClick={() => setDate(d)}>
                  {words.dayTitle(d)}
                </Chip>
              ))}
            </ChipGroup>
          </fieldset>
          {dayOpen ? (
            <>
              <fieldset className="grid gap-2">
                <legend className="mb-2 text-sm font-medium">{t("reservas.block.quick")}</legend>
                <ChipGroup label={t("reservas.block.quick")}>
                  {shifts.map((s) => {
                    const own = slots.filter((x) => x.shift === s.name).map((x) => x.time);
                    const first = own[0] ?? s.from;
                    const last = own[own.length - 1] ?? s.to;
                    return (
                      <Chip
                        key={s.name}
                        pressed={from === first && until === last}
                        onClick={() => {
                          setFrom(first);
                          setUntil(last);
                        }}
                      >
                        {t("reservas.block.shift", { name: s.name.toLocaleLowerCase() })}
                      </Chip>
                    );
                  })}
                  <Chip
                    pressed={from === times[0] && until === times[times.length - 1]}
                    onClick={() => {
                      setFrom(times[0]!);
                      setUntil(times[times.length - 1]!);
                    }}
                  >
                    {t("reservas.block.allDay")}
                  </Chip>
                </ChipGroup>
              </fieldset>
              <div className="grid grid-cols-2 gap-4">
                <Field label={t("reservas.block.from")}>
                  {(a11y) => (
                    <NativeSelect
                      {...a11y}
                      value={from}
                      onChange={(e) => {
                        setFrom(e.target.value);
                        if (until < e.target.value) setUntil(e.target.value);
                      }}
                      wrapperClassName="w-full"
                    >
                      {times.map((x) => (
                        <option key={x} value={x}>
                          {x}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </Field>
                <Field label={t("reservas.block.until")}>
                  {(a11y) => (
                    <NativeSelect {...a11y} value={until} onChange={(e) => setUntil(e.target.value)} wrapperClassName="w-full">
                      {times
                        .filter((x) => x >= from)
                        .map((x) => (
                          <option key={x} value={x}>
                            {x}
                          </option>
                        ))}
                    </NativeSelect>
                  )}
                </Field>
              </div>
              <Field
                label={t("reservas.block.label")}
                required
                requiredLabel={t("reservas.required")}
                error={touched && !label.trim() ? t("reservas.block.labelRequired") : null}
              >
                {(a11y) => <Input {...a11y} value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} />}
              </Field>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{t("reservas.block.noTimes")}</p>
          )}
          {error ? (
            <p role="alert" className="text-sm text-destructive text-pretty">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={!ready}>
              {t("reservas.block.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
