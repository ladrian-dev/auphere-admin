"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Checkbox, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Input, Label, Skeleton } from "@nexus/ui";

import { createBookingAction, moveBookingAction, serviceSlotsAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { Booking } from "@/lib/backend/reservas";

import { useReservas, useWords, type NewPrefill } from "../context";
import { formatMinutes, fromMinutes, openDays, toMinutes, weekdayOf } from "../model/dates";
import { useIdempotencyKey } from "../model/idempotency";
import { useActionLoad } from "../model/use-load";
import { failureMessage, firstName } from "../model/vocab";
import { Chip, ChipGroup } from "../shared";

export const PHONE_RE = /^\+?[0-9 ()-]{6,24}$/;

/**
 * «Nueva reserva» and «Mover la reserva» of Servicios (spec 043, T023): the
 * same dialog. Time chips are the **real** openings (`GET /slots`, never
 * computed here); a 409 `slot_taken` reads the openings again and says so.
 * The Idempotency-Key is kept while the same booking is retried.
 */
export function ServicesBookingDialog({
  booking,
  prefill,
  onClose,
}: {
  /** Moving this booking; `null` = a new one. */
  booking: Booking | null;
  prefill: NewPrefill;
  onClose: () => void;
}) {
  const { t, data, settings, today, refresh } = useReservas();
  const words = useWords();
  const key = useIdempotencyKey();
  const moving = booking !== null;
  const services = data.services ?? [];
  const team = data.staff ?? [];

  const [name, setName] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [serviceId, setServiceId] = React.useState<string>(booking?.service?.id ?? (services.length === 1 ? services[0]!.id : ""));
  const [staffId, setStaffId] = React.useState<string>(booking?.staff?.id ?? prefill.staffId ?? "");
  const [date, setDate] = React.useState<string>(booking?.local.date ?? prefill.date ?? today);
  const [time, setTime] = React.useState<string>(moving ? "" : (prefill.time ?? ""));
  const [joinWaitlist, setJoinWaitlist] = React.useState(true);
  const [notify, setNotify] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [reload, setReload] = React.useState(0);

  const service = services.find((s) => s.id === serviceId) ?? null;
  const doers = team.filter((p) => !service || service.staff === "all" || service.staff_ids.includes(p.id));
  const shownServices = services.filter((s) => !staffId || s.staff === "all" || s.staff_ids.includes(staffId));
  const days = openDays(today, 12, (d) => settings.business_hours[weekdayOf(d)].length > 0, date);

  const slots = useActionLoad(
    serviceId && date ? `${serviceId}|${staffId}|${date}|${booking?.id ?? ""}|${reload}` : null,
    () => serviceSlotsAction({ date, service_id: serviceId, staff_id: staffId || undefined, exclude: booking?.id }),
  );

  const times = slots.kind === "ok" ? slots.data.slots : [];
  // A prefilled hour that is not free (any more) is simply not chosen: the summary asks for one.
  const chosen = times.find((s) => s.time === time) ?? null;

  const staffFor = chosen ? (staffId || chosen.staff_ids[0] || "") : staffId;
  const staffName = team.find((p) => p.id === staffFor)?.name ?? "";
  const nameError = !moving && touched && !name.trim() ? t("reservas.form.nameRequired") : null;
  const phoneError = !moving && touched && phone.trim() && !PHONE_RE.test(phone.trim()) ? t("reservas.form.phoneInvalid") : null;
  const ready = !!chosen && !!service && !!staffFor && (moving || (name.trim() !== "" && (!phone.trim() || PHONE_RE.test(phone.trim()))));
  const contactName = booking?.contact.name ?? "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!ready || !service || !chosen) return;
    setBusy(true);
    try {
      const res = booking
        ? await moveBookingAction({
            id: booking.id,
            version: booking.version,
            date,
            time,
            staff_id: staffFor,
            notify: !!booking.contact.phone && notify,
          })
        : await (() => {
            const payload = {
              date,
              time,
              staff_id: staffFor,
              service_id: service.id,
              contact: { name: name.trim(), phone: phone.trim() || null },
              note: null,
              join_waitlist: settings.waitlist.enabled && joinWaitlist,
              notify: true,
            };
            return createBookingAction({ ...payload, idempotencyKey: key.take(payload) });
          })();
      if (res.ok) {
        key.done();
        toast.success(t(moving ? "reservas.form.moved" : "reservas.form.saved", { when: words.at(date, time) }));
        refresh();
        onClose();
        return;
      }
      const f = failureMessage(res);
      setError(t(f.key as MessageKey, f.vars));
      if (res.status === 409 && res.code === "slot_taken") {
        setTime("");
        setReload((n) => n + 1);
      }
      if (res.status === 412) refresh();
    } catch {
      setError(t("common.error.backend"));
    } finally {
      setBusy(false);
    }
  }

  const end = chosen && service ? fromMinutes(toMinutes(time) + service.duration_minutes) : "";

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{moving ? t("reservas.form.move.title") : t("reservas.new")}</DialogTitle>
            <DialogDescription>
              {booking
                ? t("reservas.form.move.subtitle", {
                    name: contactName,
                    service: booking.service?.name ?? "",
                    when: words.at(booking.local.date, booking.local.start),
                  })
                : t("reservas.form.new.subtitle")}
            </DialogDescription>
          </DialogHeader>

          {!moving ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("reservas.form.client")} required requiredLabel={t("reservas.required")} error={nameError}>
                {(a11y) => (
                  <Input {...a11y} value={name} onChange={(e) => setName(e.target.value)} onBlur={() => setTouched(true)} placeholder={t("reservas.form.client.placeholder")} autoComplete="off" maxLength={120} />
                )}
              </Field>
              <Field label={t("reservas.form.phone")} optionalLabel={t("reservas.optional")} hint={t("reservas.form.phone.hint")} error={phoneError}>
                {(a11y) => (
                  <Input {...a11y} type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} onBlur={() => setTouched(true)} placeholder={t("reservas.form.phone.placeholder")} autoComplete="off" maxLength={32} />
                )}
              </Field>
            </div>
          ) : null}

          {!moving ? (
            <fieldset className="grid gap-2">
              <legend className="mb-2 text-sm font-medium">{t("reservas.form.service")}</legend>
              <ChipGroup label={t("reservas.form.service")}>
                {shownServices.map((s) => (
                  <Chip key={s.id} pressed={s.id === serviceId} onClick={() => setServiceId(s.id)}>
                    <span className="truncate">{t("reservas.form.serviceChip", { name: s.name, duration: formatMinutes(s.duration_minutes) })}</span>
                  </Chip>
                ))}
              </ChipGroup>
            </fieldset>
          ) : null}

          {doers.length > 1 ? (
            <fieldset className="grid gap-2">
              <legend className="mb-2 text-sm font-medium">{t("reservas.form.staff")}</legend>
              <ChipGroup label={t("reservas.form.staff")}>
                {!moving ? (
                  <Chip pressed={staffId === ""} onClick={() => setStaffId("")}>
                    {t("reservas.form.staff.any")}
                  </Chip>
                ) : null}
                {doers.map((p) => (
                  <Chip key={p.id} pressed={p.id === staffId} onClick={() => setStaffId(p.id)}>
                    <span className="truncate">{p.name}</span>
                  </Chip>
                ))}
              </ChipGroup>
            </fieldset>
          ) : null}

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

          <fieldset className="grid gap-2" aria-busy={slots.kind === "loading" || undefined}>
            <legend className="mb-2 text-sm font-medium">{t("reservas.form.time")}</legend>
            {slots.kind === "idle" ? (
              <p className="text-sm text-muted-foreground">{t("reservas.form.slots.pickService")}</p>
            ) : slots.kind === "loading" ? (
              <div role="status" aria-label={t("reservas.form.slots.loading")} className="flex flex-wrap gap-2">
                {Array.from({ length: 8 }, (_, i) => (
                  <Skeleton key={i} className="h-8 w-16 rounded-full" />
                ))}
              </div>
            ) : slots.kind === "error" ? (
              <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-destructive">{t("reservas.form.slots.error")}</span>
                <Button type="button" size="sm" variant="outline" onClick={() => setReload((n) => n + 1)}>
                  {t("common.retry")}
                </Button>
              </div>
            ) : slots.data.closed ? (
              <p className="text-sm text-muted-foreground">{t("reservas.form.slots.closed")}</p>
            ) : times.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("reservas.form.slots.none")}</p>
            ) : (
              <ChipGroup label={t("reservas.form.time")}>
                {times.map((s) => (
                  <Chip key={s.time} pressed={s.time === time} onClick={() => setTime(s.time)} className="tabular-nums">
                    {s.time}
                  </Chip>
                ))}
              </ChipGroup>
            )}
          </fieldset>

          {!moving && settings.waitlist.enabled ? (
            <div className="flex items-start gap-3">
              <Checkbox id="reservas-join-waitlist" checked={joinWaitlist} onCheckedChange={(v) => setJoinWaitlist(v === true)} className="mt-1" />
              <div className="grid gap-1">
                <Label htmlFor="reservas-join-waitlist">{t("reservas.form.waitlist")}</Label>
                <p className="text-xs text-muted-foreground">{t("reservas.form.waitlist.hint")}</p>
              </div>
            </div>
          ) : null}

          {booking?.contact.phone ? (
            <div className="flex items-center gap-3">
              <Checkbox id="reservas-notify-move" checked={notify} onCheckedChange={(v) => setNotify(v === true)} />
              <Label htmlFor="reservas-notify-move">{t("reservas.form.notifyMove", { name: firstName(contactName) })}</Label>
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm text-destructive text-pretty">
              {error}
            </p>
          ) : null}

          <DialogFooter className="items-center sm:justify-between">
            <p className="min-w-0 text-sm text-muted-foreground" aria-live="polite">
              {chosen
                ? t("reservas.form.summary.services", { day: words.dayTitle(date), from: time, to: end, name: staffName })
                : t("reservas.form.summary.pick")}
            </p>
            <Button type="submit" loading={busy} disabled={!ready}>
              {moving ? t("reservas.form.move.save") : t("reservas.form.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
