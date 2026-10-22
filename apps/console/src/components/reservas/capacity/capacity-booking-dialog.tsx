"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Input, Skeleton, Textarea, cn } from "@nexus/ui";

import { capacitySlotsAction, createBookingAction, moveBookingAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { Booking, CapacitySlot } from "@/lib/backend/reservas";

import { useReservas, useWords, type NewPrefill } from "../context";
import { openDays, weekdayOf } from "../model/dates";
import { useIdempotencyKey } from "../model/idempotency";
import { useActionLoad } from "../model/use-load";
import { failureMessage } from "../model/vocab";
import { PHONE_RE } from "../services/booking-dialog";
import { Chip, ChipGroup, Stepper } from "../shared";

/** Slots grouped under their shift, in order (one unnamed group for the «franjas» model). */
export function slotsByShift(slots: readonly CapacitySlot[]): { shift: string | null; slots: CapacitySlot[] }[] {
  const out: { shift: string | null; slots: CapacitySlot[] }[] = [];
  for (const s of slots) {
    const last = out[out.length - 1];
    if (last && last.shift === s.shift) last.slots.push(s);
    else out.push({ shift: s.shift, slots: [s] });
  }
  return out;
}

/**
 * «Nueva reserva» and «Cambiar reserva» of Aforo (spec 043, T024): name,
 * optional phone, −/+ people (the business may go over the agent's maximum,
 * and is told so), the next 10 open days, and the arrival times per shift
 * with «quedan N» or why not — from `GET /slots`, never computed here.
 * «Cambiar» shows the note there is and sends it only when it changed
 * (enmienda 2026-10-22: absent leaves it, `null` clears it).
 */
export function CapacityBookingDialog({ booking, prefill, onClose }: { booking: Booking | null; prefill: NewPrefill; onClose: () => void }) {
  const { t, settings, today, refresh } = useReservas();
  const words = useWords();
  const key = useIdempotencyKey();
  const moving = booking !== null;
  const maxParty = settings.capacity?.max_party ?? 0;

  const [name, setName] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [people, setPeople] = React.useState(booking?.party_size ?? 2);
  const [date, setDate] = React.useState(booking?.local.date ?? prefill.date ?? today);
  const [time, setTime] = React.useState(moving ? "" : (prefill.time ?? ""));
  const [note, setNote] = React.useState(booking?.note ?? "");
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [reload, setReload] = React.useState(0);
  const days = openDays(today, 10, (d) => settings.business_hours[weekdayOf(d)].length > 0, date);

  // −/+ moves fast: the read waits a beat so each click does not ask again.
  const slots = useActionLoad(
    `${date}|${people}|${booking?.id ?? ""}|${reload}`,
    () => capacitySlotsAction({ date, party_size: people, exclude: booking?.id }),
    { delayMs: 200 },
  );

  const all = slots.kind === "ok" ? slots.data.slots : [];
  const chosen = all.find((s) => s.time === time && s.fits) ?? null;

  const nameOk = moving || name.trim() !== "";
  const phoneOk = moving || !phone.trim() || PHONE_RE.test(phone.trim());
  const ready = !!chosen && nameOk && phoneOk;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!ready) return;
    setBusy(true);
    try {
      const nextNote = note.trim() || null;
      const res = booking
        ? await moveBookingAction({
            id: booking.id,
            version: booking.version,
            date,
            time,
            party_size: people,
            ...(nextNote !== (booking.note?.trim() || null) ? { note: nextNote } : {}),
            notify: !!booking.contact.phone,
          })
        : await (() => {
            const payload = {
              date,
              time,
              party_size: people,
              contact: { name: name.trim(), phone: phone.trim() || null },
              note: nextNote,
              join_waitlist: false,
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

  const unitTitle = t(`reservas.kind.${settings.capacity_kind ?? "restaurant"}.unitTitle` as MessageKey);
  const slotState = (s: CapacitySlot) => (s.fits ? t("reservas.aform.left", { count: s.left }) : t(`reservas.slot.why.${s.why ?? "full"}` as MessageKey));

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{moving ? t("reservas.aform.move.title") : t("reservas.new")}</DialogTitle>
            <DialogDescription>
              {moving
                ? booking?.contact.phone
                  ? t("reservas.aform.move.subtitle")
                  : t("reservas.aform.move.subtitleNoPhone")
                : t("reservas.aform.new.subtitle")}
            </DialogDescription>
          </DialogHeader>

          {!moving ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label={t("reservas.aform.name")}
                required
                requiredLabel={t("reservas.required")}
                error={touched && !nameOk ? t("reservas.form.nameRequired") : null}
              >
                {(a11y) => <Input {...a11y} value={name} onChange={(e) => setName(e.target.value)} onBlur={() => setTouched(true)} maxLength={120} autoComplete="off" />}
              </Field>
              <Field
                label={t("reservas.form.phone")}
                optionalLabel={t("reservas.optional")}
                error={touched && !phoneOk ? t("reservas.form.phoneInvalid") : null}
              >
                {(a11y) => (
                  <Input {...a11y} type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} onBlur={() => setTouched(true)} placeholder={t("reservas.form.phone.placeholder")} maxLength={32} autoComplete="off" />
                )}
              </Field>
            </div>
          ) : null}

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{unitTitle}</span>
              <Stepper label={unitTitle} value={people} onChange={setPeople} min={1} max={settings.capacity?.seats} />
            </div>
            {maxParty > 0 && people > maxParty ? (
              <p className="text-xs text-warning text-pretty">{t("reservas.aform.overMax", { max: maxParty })}</p>
            ) : null}
          </div>

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

          <fieldset className="grid gap-3" aria-busy={slots.kind === "loading" || undefined}>
            <legend className="mb-2 text-sm font-medium">{t("reservas.form.time")}</legend>
            {slots.kind === "loading" || slots.kind === "idle" ? (
              <div role="status" aria-label={t("reservas.form.slots.loading")} className="flex flex-wrap gap-2">
                {Array.from({ length: 8 }, (_, i) => (
                  <Skeleton key={i} className="h-12 w-20" />
                ))}
              </div>
            ) : slots.kind === "error" ? (
              <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-destructive">{t("reservas.form.slots.error")}</span>
                <Button type="button" size="sm" variant="outline" onClick={() => setReload((n) => n + 1)}>
                  {t("common.retry")}
                </Button>
              </div>
            ) : slots.data.closed || all.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("reservas.form.slots.closed")}</p>
            ) : !all.some((s) => s.fits) ? (
              <p className="text-sm text-muted-foreground">{t("reservas.aform.noTimes", { count: people, unit: words.unitFor(people) })}</p>
            ) : (
              slotsByShift(all).map((g) => (
                <div key={g.shift ?? "slots"} className="grid gap-2">
                  <span className="text-xs font-medium text-muted-foreground">{g.shift ?? t("reservas.aform.slots")}</span>
                  <ChipGroup label={g.shift ?? t("reservas.aform.slots")}>
                    {g.slots.map((s) => (
                      <button
                        key={s.time}
                        type="button"
                        aria-pressed={s.time === time}
                        disabled={!s.fits}
                        aria-label={t("reservas.slot.aria", { time: s.time, state: slotState(s) })}
                        onClick={() => setTime(s.time)}
                        className={cn(
                          "flex h-12 min-w-20 flex-col items-center justify-center rounded-md border px-2 text-sm tabular-nums",
                          "transition-colors duration-(--duration-hover) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                          "disabled:cursor-not-allowed disabled:opacity-50",
                          s.time === time ? "border-transparent bg-accent font-medium text-accent-foreground" : "border-border bg-background hover:bg-muted",
                        )}
                      >
                        <span>{s.time}</span>
                        <span className="text-xs text-muted-foreground">{slotState(s)}</span>
                      </button>
                    ))}
                  </ChipGroup>
                </div>
              ))
            )}
          </fieldset>

          <Field label={t("reservas.aform.note")} optionalLabel={t("reservas.optional")}>
            {(a11y) => (
              <Textarea {...a11y} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("reservas.aform.note.placeholder")} maxLength={500} rows={2} />
            )}
          </Field>

          {error ? (
            <p role="alert" className="text-sm text-destructive text-pretty">
              {error}
            </p>
          ) : null}

          <DialogFooter className="items-center sm:justify-between">
            <p className="min-w-0 text-sm text-muted-foreground" aria-live="polite">
              {chosen ? t("reservas.aform.summary", { people: words.people(people), when: words.at(date, time) }) : t("reservas.form.summary.pick")}
            </p>
            <Button type="submit" loading={busy} disabled={!ready}>
              {moving ? t("reservas.aform.saveChanges") : t("reservas.form.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
