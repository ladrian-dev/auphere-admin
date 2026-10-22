"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Input } from "@nexus/ui";

import { addWaitlistAction } from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";

import { useReservas } from "../context";
import { addDays, formatMinutes, isDay } from "../model/dates";
import { useIdempotencyKey } from "../model/idempotency";
import { failureMessage } from "../model/vocab";
import { PHONE_RE } from "../services/booking-dialog";
import { Chip } from "../shared";

/** «Cualquier hueco hasta» starts a week ahead: the design's «Cualquier hueco esta semana». */
const DEFAULT_UNTIL_DAYS = 7;

/**
 * «Apuntar a alguien» of Servicios (spec 043, T025; design §3.1 «el equipo
 * también puede apuntar»): a loose entry, without a booking — the name, the
 * phone if there is one (without it nobody can be told on WhatsApp), the
 * service, «Con» someone or anyone, and the last day any opening is good
 * for. `POST /waitlist` with the submit's Idempotency-Key, kept on a retry.
 */
export function AddWaitlistDialog({ onClose }: { onClose: () => void }) {
  const { t, data, settings, today, refresh } = useReservas();
  const key = useIdempotencyKey();
  const services = data.services ?? [];
  const team = data.staff ?? [];

  const [name, setName] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [serviceId, setServiceId] = React.useState(services.length === 1 ? services[0]!.id : "");
  const [staffId, setStaffId] = React.useState("");
  const [until, setUntil] = React.useState(addDays(today, DEFAULT_UNTIL_DAYS));
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const service = services.find((s) => s.id === serviceId) ?? null;
  const doers = team.filter((p) => !service || service.staff === "all" || service.staff_ids.includes(p.id));
  // Someone who does not do the chosen service is not a choice any more: anyone.
  const staffFor = doers.some((p) => p.id === staffId) ? staffId : "";
  const lastDay = addDays(today, settings.agent.max_days_ahead);

  const nameOk = name.trim() !== "";
  const phoneOk = !phone.trim() || PHONE_RE.test(phone.trim());
  const untilOk = isDay(until) && until >= today;
  const ready = nameOk && phoneOk && !!service && untilOk;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!ready || !service) return;
    setBusy(true);
    try {
      const payload = { name: name.trim(), phone: phone.trim() || null, service_id: service.id, staff_id: staffFor || null, date: null, until };
      const res = await addWaitlistAction({ ...payload, idempotencyKey: key.take(payload) });
      if (res.ok) {
        key.done();
        toast.success(t("reservas.wl.add.done", { name: payload.name }));
        refresh();
        onClose();
        return;
      }
      const f = failureMessage(res);
      setError(t(f.key as MessageKey, f.vars));
      if (res.status === 412) refresh();
    } catch {
      setError(t("common.error.backend"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{t("reservas.wl.add.title")}</DialogTitle>
            <DialogDescription>{t("reservas.wl.add.subtitle")}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={t("reservas.form.client")}
              required
              requiredLabel={t("reservas.required")}
              error={touched && !nameOk ? t("reservas.wl.add.nameRequired") : null}
            >
              {(a11y) => (
                <Input
                  {...a11y}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("reservas.form.client.placeholder")}
                  autoComplete="off"
                  maxLength={120}
                />
              )}
            </Field>
            <Field
              label={t("reservas.form.phone")}
              optionalLabel={t("reservas.optional")}
              hint={t("reservas.wl.add.phone.hint")}
              error={touched && !phoneOk ? t("reservas.form.phoneInvalid") : null}
            >
              {(a11y) => (
                <Input
                  {...a11y}
                  type="tel"
                  inputMode="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder={t("reservas.form.phone.placeholder")}
                  autoComplete="off"
                  maxLength={32}
                />
              )}
            </Field>
          </div>

          <fieldset className="grid gap-2" aria-describedby={touched && !service ? "reservas-wl-add-service-error" : undefined}>
            <legend className="mb-2 text-sm font-medium">{t("reservas.form.service")}</legend>
            <div className="flex min-w-0 flex-wrap gap-2">
              {services.map((s) => (
                <Chip key={s.id} pressed={s.id === serviceId} onClick={() => setServiceId(s.id)}>
                  <span className="truncate">{t("reservas.form.serviceChip", { name: s.name, duration: formatMinutes(s.duration_minutes) })}</span>
                </Chip>
              ))}
            </div>
            {touched && !service ? (
              <p id="reservas-wl-add-service-error" role="alert" className="text-xs text-destructive text-pretty">
                {t("reservas.wl.add.serviceRequired")}
              </p>
            ) : null}
          </fieldset>

          {doers.length > 1 ? (
            <fieldset className="grid gap-2">
              <legend className="mb-2 text-sm font-medium">{t("reservas.form.staff")}</legend>
              <div className="flex min-w-0 flex-wrap gap-2">
                <Chip pressed={staffFor === ""} onClick={() => setStaffId("")}>
                  {t("reservas.form.staff.any")}
                </Chip>
                {doers.map((p) => (
                  <Chip key={p.id} pressed={p.id === staffFor} onClick={() => setStaffId(p.id)}>
                    <span className="truncate">{p.name}</span>
                  </Chip>
                ))}
              </div>
            </fieldset>
          ) : null}

          <Field
            label={t("reservas.wl.add.until")}
            hint={t("reservas.wl.add.until.hint")}
            error={touched && !untilOk ? t("reservas.wl.add.untilInvalid") : null}
            className="sm:max-w-60"
          >
            {(a11y) => <Input {...a11y} type="date" min={today} max={lastDay} value={until} onChange={(e) => setUntil(e.target.value)} />}
          </Field>

          {error ? (
            <p role="alert" className="text-sm text-destructive text-pretty">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={busy}>
              {t("reservas.wl.add.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
