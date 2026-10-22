"use client";

import { Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Checkbox,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  Label,
  NativeSelect,
  Section,
  Switch,
} from "@nexus/ui";

import {
  archiveServiceAction,
  archiveStaffAction,
  createServiceAction,
  createStaffAction,
  updateServiceAction,
  updateStaffAction,
} from "@/app/(console)/reservas/actions";
import type { MessageKey } from "@/i18n/messages";
import type { ReservasService, StaffMember, WeekHours } from "@/lib/backend/reservas";

import { useReservas } from "../context";
import { formatMinutes } from "../model/dates";
import { sameWeek, weekInvalidDays } from "../model/hours";
import { useIdempotencyKey } from "../model/idempotency";
import { formatPrice, parsePrice, priceInput } from "../model/money";
import { failureMessage } from "../model/vocab";
import { Initials } from "../shared";
import { HoursEditor } from "./hours-editor";
import { BusinessHoursSection, SwitchRow, WaitlistSettings, useSettingsPatch } from "./shared-sections";

/** The lengths a service can have in the design: 30 min to 3 h. */
export const DURATIONS = [30, 45, 60, 90, 120, 180] as const;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Ajustes of Servicios (spec 043, T025): the waitlist, reminders, the
 * business's hours, the team with their hours, and the services.
 */
export function ServicesSettings() {
  return (
    <div className="grid min-w-0 gap-6 xl:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-6">
        <WaitlistSettings />
        <Reminders />
        <BusinessHoursSection />
      </div>
      <div className="flex min-w-0 flex-col gap-6">
        <TeamSection />
        <ServicesSection />
      </div>
    </div>
  );
}

function Reminders() {
  const { t, settings } = useReservas();
  const { patch, busy } = useSettingsPatch();
  return (
    <Section title={t("reservas.settings.reminders.title")}>
      <SwitchRow
        id="reservas-reminder"
        label={t("reservas.settings.reminder")}
        hint={t("reservas.settings.reminder.hint")}
        checked={settings.reminder_enabled}
        disabled={busy}
        onChange={(on) => void patch({ reminder_enabled: on })}
      />
      <SwitchRow
        id="reservas-ask-confirm"
        label={t("reservas.settings.askConfirm")}
        hint={t("reservas.settings.askConfirm.hint")}
        checked={settings.confirmation.enabled}
        disabled={busy}
        onChange={(on) => void patch({ confirmation: { enabled: on } })}
      />
    </Section>
  );
}

function useArchive() {
  const { t, refresh } = useReservas();
  const [error, setError] = React.useState<string | null>(null);
  const run = React.useCallback(
    async (fn: () => Promise<{ ok: boolean; status?: number; code?: string | null; info?: Record<string, unknown> }>, done: string) => {
      setError(null);
      try {
        const res = await fn();
        if (res.ok) {
          toast.success(done);
          refresh();
          return true;
        }
        const f = failureMessage(res as { status: number; code?: string | null; info?: Record<string, unknown> });
        setError(t(f.key as MessageKey, f.vars));
      } catch {
        setError(t("common.error.backend"));
      }
      return false;
    },
    [t, refresh],
  );
  return { run, error, clear: () => setError(null) };
}

function TeamSection() {
  const { t, data, settings } = useReservas();
  const [editing, setEditing] = React.useState<StaffMember | "new" | null>(null);
  const [archiving, setArchiving] = React.useState<StaffMember | null>(null);
  const archive = useArchive();
  const staff = data.staff;
  return (
    <Section
      title={t("reservas.team.title")}
      description={staff ? (staff.length === 1 ? t("reservas.count.people.one") : t("reservas.count.people.other", { count: staff.length })) : undefined}
      actions={
        <Button size="sm" variant="outline" onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" />
          {t("reservas.team.add")}
        </Button>
      }
    >
      {staff === null ? (
        <p className="text-sm text-muted-foreground">{t("reservas.settings.partError")}</p>
      ) : staff.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.team.empty")}</p>
      ) : (
        <ul className="flex min-w-0 flex-col divide-y divide-border">
          {staff.map((s) => (
            <li key={s.id} className="flex min-w-0 flex-wrap items-center gap-3 py-2">
              <Initials name={s.name} />
              <span className="flex min-w-0 flex-1 basis-32 flex-col">
                <span className="truncate text-sm font-medium" title={s.name}>
                  {s.name}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {s.hours === null || sameWeek(s.hours, settings.business_hours) ? t("reservas.team.hours.business") : t("reservas.team.hours.own")}
                  {s.email ? ` · ${s.email}` : ""}
                </span>
              </span>
              <span className="flex shrink-0 gap-1">
                <Button size="xs" variant="ghost" aria-label={t("reservas.team.edit.aria", { name: s.name })} onClick={() => setEditing(s)}>
                  {t("reservas.settings.hours.edit")}
                </Button>
                <Button size="xs" variant="ghost" aria-label={t("reservas.team.archive.aria", { name: s.name })} onClick={() => setArchiving(s)}>
                  {t("reservas.team.archive")}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {editing ? <StaffDialog member={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      <ConfirmDialog
        open={archiving !== null}
        onOpenChange={(o) => {
          if (!o) {
            setArchiving(null);
            archive.clear();
          }
        }}
        title={archiving ? t("reservas.team.archive.title", { name: archiving.name }) : ""}
        description={t("reservas.team.archive.body")}
        confirmLabel={t("reservas.team.archive")}
        cancelLabel={t("common.cancel")}
        destructive
        error={archive.error}
        onConfirm={async () => {
          if (archiving && (await archive.run(() => archiveStaffAction({ id: archiving.id }), t("reservas.team.archived")))) setArchiving(null);
        }}
      />
    </Section>
  );
}

function StaffDialog({ member, onClose }: { member: StaffMember | null; onClose: () => void }) {
  const { t, settings, refresh } = useReservas();
  const key = useIdempotencyKey();
  const [name, setName] = React.useState(member?.name ?? "");
  const [email, setEmail] = React.useState(member?.email ?? "");
  const [ownHours, setOwnHours] = React.useState(member?.hours != null);
  const [week, setWeek] = React.useState<WeekHours>(member?.hours ?? member?.effective_hours ?? settings.business_hours);
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const emailOk = !email.trim() || EMAIL_RE.test(email.trim());
  const ready = name.trim() !== "" && emailOk && (!ownHours || weekInvalidDays(week).length === 0);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!ready) return;
    setBusy(true);
    const body = { name: name.trim(), email: email.trim() || null, hours: ownHours ? week : null };
    try {
      const res = member
        ? await updateStaffAction({ id: member.id, ...body })
        : await createStaffAction({ ...body, idempotencyKey: key.take(body) });
      if (res.ok) {
        key.done();
        toast.success(t("reservas.settings.saved"));
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
        <form onSubmit={save} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{member ? t("reservas.team.edit") : t("reservas.team.add")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("reservas.team.name")} required requiredLabel={t("reservas.required")} error={touched && !name.trim() ? t("reservas.form.nameRequired") : null}>
              {(a11y) => <Input {...a11y} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="off" />}
            </Field>
            <Field
              label={t("reservas.team.email")}
              optionalLabel={t("reservas.optional")}
              hint={t("reservas.team.email.hint")}
              error={touched && !emailOk ? t("reservas.team.email.invalid") : null}
            >
              {(a11y) => <Input {...a11y} type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} autoComplete="off" />}
            </Field>
          </div>
          <div className="flex items-center gap-3">
            <Switch id="reservas-staff-business" checked={!ownHours} onCheckedChange={(on) => setOwnHours(!on)} aria-labelledby="reservas-staff-business-label" />
            <Label id="reservas-staff-business-label" htmlFor="reservas-staff-business">
              {t("reservas.team.useBusiness")}
            </Label>
          </div>
          {ownHours ? <HoursEditor value={week} onChange={setWeek} /> : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={!ready && touched}>
              {t("reservas.settings.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ServicesSection() {
  const { t, locale, data } = useReservas();
  const [editing, setEditing] = React.useState<ReservasService | "new" | null>(null);
  const [archiving, setArchiving] = React.useState<ReservasService | null>(null);
  const archive = useArchive();
  const services = data.services;
  const staffName = (id: string) => data.staff?.find((s) => s.id === id)?.name;
  return (
    <Section
      title={t("reservas.svc.title")}
      actions={
        <Button size="sm" variant="outline" onClick={() => setEditing("new")}>
          <Plus aria-hidden="true" />
          {t("reservas.svc.add")}
        </Button>
      }
    >
      {services === null ? (
        <p className="text-sm text-muted-foreground">{t("reservas.settings.partError")}</p>
      ) : services.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("reservas.svc.empty")}</p>
      ) : (
        <ul className="flex min-w-0 flex-col divide-y divide-border">
          {services.map((s) => (
            <li key={s.id} className="flex min-w-0 flex-wrap items-center gap-3 py-2">
              <span className="flex min-w-0 flex-1 basis-40 flex-col">
                <span className="truncate text-sm font-medium" title={s.name}>
                  {s.name}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {formatMinutes(s.duration_minutes)} · {formatPrice(s.price, locale) ?? t("reservas.svc.noCost")} ·{" "}
                  {s.staff === "all" ? t("reservas.svc.who.all") : s.staff_ids.map(staffName).filter(Boolean).join(", ")}
                </span>
              </span>
              <span className="flex shrink-0 gap-1">
                <Button size="xs" variant="ghost" aria-label={t("reservas.svc.edit.aria", { name: s.name })} onClick={() => setEditing(s)}>
                  {t("reservas.settings.hours.edit")}
                </Button>
                <Button size="xs" variant="ghost" aria-label={t("reservas.svc.archive.aria", { name: s.name })} onClick={() => setArchiving(s)}>
                  {t("reservas.team.archive")}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {editing ? <ServiceDialog service={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      <ConfirmDialog
        open={archiving !== null}
        onOpenChange={(o) => {
          if (!o) {
            setArchiving(null);
            archive.clear();
          }
        }}
        title={archiving ? t("reservas.svc.archive.title", { name: archiving.name }) : ""}
        description={t("reservas.svc.archive.body")}
        confirmLabel={t("reservas.team.archive")}
        cancelLabel={t("common.cancel")}
        destructive
        error={archive.error}
        onConfirm={async () => {
          if (archiving && (await archive.run(() => archiveServiceAction({ id: archiving.id }), t("reservas.svc.archived")))) setArchiving(null);
        }}
      />
    </Section>
  );
}

function ServiceDialog({ service, onClose }: { service: ReservasService | null; onClose: () => void }) {
  const { t, data, settings, refresh } = useReservas();
  const key = useIdempotencyKey();
  const currency = service?.price?.currency ?? settings.currency;
  const team = data.staff ?? [];
  const [name, setName] = React.useState(service?.name ?? "");
  const [duration, setDuration] = React.useState<number>(service?.duration_minutes ?? 30);
  const [price, setPrice] = React.useState(priceInput(service?.price?.amount_minor, currency));
  const [who, setWho] = React.useState<"all" | "some">(service?.staff ?? "all");
  const [some, setSome] = React.useState<string[]>(service?.staff_ids ?? []);
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const parsed = parsePrice(price, currency);
  const durations = DURATIONS.includes(duration as (typeof DURATIONS)[number]) ? [...DURATIONS] : [...DURATIONS, duration].sort((a, b) => a - b);
  const ready = name.trim() !== "" && parsed.kind !== "invalid" && (who === "all" || some.length > 0);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    if (!ready) return;
    setBusy(true);
    const body = {
      name: name.trim(),
      duration_minutes: duration,
      price_minor: parsed.kind === "ok" ? parsed.minor : null,
      staff_ids: who === "all" ? null : some,
    };
    try {
      const res = service
        ? await updateServiceAction({ id: service.id, ...body })
        : await createServiceAction({ ...body, idempotencyKey: key.take(body) });
      if (res.ok) {
        key.done();
        toast.success(t("reservas.settings.saved"));
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
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={save} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{service ? t("reservas.svc.edit") : t("reservas.svc.add")}</DialogTitle>
          </DialogHeader>
          <Field label={t("reservas.svc.name")} required requiredLabel={t("reservas.required")} error={touched && !name.trim() ? t("reservas.form.nameRequired") : null}>
            {(a11y) => <Input {...a11y} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("reservas.svc.name.placeholder")} maxLength={120} />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("reservas.svc.duration")}>
              {(a11y) => (
                <NativeSelect {...a11y} value={duration} onChange={(e) => setDuration(Number(e.target.value))} wrapperClassName="w-full">
                  {durations.map((m) => (
                    <option key={m} value={m}>
                      {formatMinutes(m)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <Field
              label={t("reservas.svc.price")}
              optionalLabel={t("reservas.optional")}
              hint={t("reservas.svc.price.hint", { currency })}
              error={parsed.kind === "invalid" ? t("reservas.svc.price.invalid") : null}
            >
              {(a11y) => <Input {...a11y} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="15000" maxLength={16} />}
            </Field>
          </div>
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">{t("reservas.svc.who")}</legend>
            <label className="flex items-center gap-3 text-sm">
              <input type="radio" name="reservas-svc-who" checked={who === "all"} onChange={() => setWho("all")} className="size-4 accent-primary" />
              {t("reservas.svc.who.all")}
            </label>
            <label className="flex items-center gap-3 text-sm">
              <input type="radio" name="reservas-svc-who" checked={who === "some"} onChange={() => setWho("some")} className="size-4 accent-primary" />
              {t("reservas.svc.who.some")}
            </label>
            {who === "some" ? (
              <ul className="grid gap-2 pl-7">
                {team.map((p) => (
                  <li key={p.id} className="flex items-center gap-3">
                    <Checkbox
                      id={`reservas-svc-${p.id}`}
                      checked={some.includes(p.id)}
                      onCheckedChange={(on) => setSome((cur) => (on ? [...cur, p.id] : cur.filter((x) => x !== p.id)))}
                    />
                    <Label htmlFor={`reservas-svc-${p.id}`}>{p.name}</Label>
                  </li>
                ))}
              </ul>
            ) : null}
            {who === "some" && touched && some.length === 0 ? (
              <p role="alert" className="text-xs text-destructive">
                {t("reservas.svc.who.none")}
              </p>
            ) : null}
          </fieldset>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={!ready && touched}>
              {t("reservas.settings.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
