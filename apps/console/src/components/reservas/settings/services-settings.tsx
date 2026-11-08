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
import { DURATIONS, byCategory, categoriesOf, priceText, samePrice } from "@/components/business/sections/services-model";
import { currencyOptions, displayName } from "@/components/clients/client-modal-model";
import { useDiscardGuard } from "@/components/use-discard-guard";
import type { MessageKey } from "@/i18n/messages";
import { amountInput, minorDigits, parseAmount } from "@/lib/amount";
import type { Price, PriceKind } from "@/lib/backend/business-sections";
import type { ReservasService, ServicePatch, StaffMember, WeekHours } from "@/lib/backend/reservas";
import { CATEGORY_MAX, NAME_MAX } from "@/lib/business-rules";

import { useReservas } from "../context";
import { formatMinutes } from "../model/dates";
import { sameWeek, weekInvalidDays } from "../model/hours";
import { useIdempotencyKey } from "../model/idempotency";
import { failureMessage } from "../model/vocab";
import { Initials } from "../shared";
import { HoursEditor } from "./hours-editor";
import { ReservasTemplatesSection } from "./reservas-templates";
import { BusinessHoursSection, SwitchRow, WaitlistSettings, useSettingsPatch } from "./shared-sections";
import { StaffCalendarsSection } from "./staff-calendars";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** RFC 5321, as the API (`reservas_schemas.EMAIL_MAX`, spec 056 11.3). */
const EMAIL_MAX = 254;
const PRICE_KINDS: readonly PriceKind[] = ["none", "free", "amount"];
/** The codes of the shared rules a service save can answer with (`business.services.error.*`). */
const SERVICE_ERRORS = new Set([
  "bad_duration",
  "duration_required",
  "price_invalid",
  "price_amount_required",
  "amount_too_large",
  "price_currency_required",
  "category_too_long",
  "name_required",
  "name_too_long",
  "rename_not_allowed",
]);

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
        <ReservasTemplatesSection />
        <BusinessHoursSection />
      </div>
      <div className="flex min-w-0 flex-col gap-6">
        <TeamSection />
        <StaffCalendarsSection />
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
                {s.warnings?.includes("no_hours") ? <span className="text-xs text-pretty text-warning">{t("reservas.team.warning.noHours")}</span> : null}
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
  const initialWeek = member?.hours ?? member?.effective_hours ?? settings.business_hours;
  const dirty =
    name !== (member?.name ?? "") || email !== (member?.email ?? "") || ownHours !== (member?.hours != null) || (ownHours && !sameWeek(week, initialWeek));
  const guard = useDiscardGuard(dirty, onClose);

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
    <>
      <Dialog open onOpenChange={guard.onOpenChange}>
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
                error={touched && !emailOk ? t("reservas.team.email.invalid") : null}
              >
                {(a11y) => <Input {...a11y} type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={EMAIL_MAX} autoComplete="off" />}
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
              <Button type="button" variant="outline" onClick={guard.close}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={busy} disabled={!ready && touched}>
                {t("reservas.settings.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {guard.dialog}
    </>
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
        <div className="grid min-w-0 gap-3">
          {byCategory(services, locale).map((group, _i, all) => (
            <div key={group.category ?? ""} className="grid min-w-0 gap-1" data-slot="service-category">
              {/* Spec 055 (requisito 7.4): sin ninguna categoría, la lista de siempre. */}
              {all.some((g) => g.category !== null) ? (
                <h3 className="text-xs font-medium text-muted-foreground">{group.category ?? t("reservas.svc.category.none")}</h3>
              ) : null}
        <ul className="flex min-w-0 flex-col divide-y divide-border">
          {group.items.map((s) => (
            <li key={s.id} className="flex min-w-0 flex-wrap items-center gap-3 py-2">
              <span className="flex min-w-0 flex-1 basis-40 flex-col">
                <span className="truncate text-sm font-medium" title={s.name}>
                  {s.name}
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {formatMinutes(s.duration_minutes)} · {priceText(s.price, s.currency, locale, { free: t("business.services.price.free"), none: t("business.services.price.none") })} ·{" "}
                  {s.staff === "all" ? t("reservas.svc.who.all") : s.staff_ids.map(staffName).filter(Boolean).join(", ")}
                </span>
                {s.warnings?.includes("no_staff") ? <span className="text-xs text-pretty text-warning">{t("reservas.svc.warning.noStaff")}</span> : null}
                {s.warnings?.includes("does_not_fit") ? <span className="text-xs text-pretty text-warning">{t("reservas.svc.warning.doesNotFit")}</span> : null}
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
            </div>
          ))}
        </div>
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

/**
 * A service of Reservas (spec 056, requisito 5): the ficha's rules — 5 to 480
 * minutes, no price, free or an amount up to 10¹², a category of 40. A new one
 * takes its name; an existing one keeps it (5.4): the name is read, not edited.
 * Editing sends only what changed (5.3), so «Gratis» stays free. A 422 is said
 * on its field, in words (5.6). Closing with changes asks first (12.3).
 */
function ServiceDialog({ service, onClose }: { service: ReservasService | null; onClose: () => void }) {
  const { t, locale, data, settings, refresh } = useReservas();
  const key = useIdempotencyKey();
  // Spec 055 (requisitos 3.1 y 3.2): un importe es de la moneda del negocio; sin
  // ninguna, se elige aquí y queda para todos sus precios.
  const unset = settings.currency_set === false;
  const [chosen, setChosen] = React.useState("");
  const currency = unset ? chosen || "USD" : (service?.currency ?? settings.currency);
  const team = data.staff ?? [];
  const [name, setName] = React.useState(service?.name ?? "");
  const [category, setCategory] = React.useState(service?.category ?? "");
  const categories = categoriesOf(data.services ?? [], locale);
  const [duration, setDuration] = React.useState<number>(service?.duration_minutes ?? 30);
  const [kind, setKind] = React.useState<PriceKind>(service?.price.kind ?? "none");
  const [amount, setAmount] = React.useState(service?.price.kind === "amount" ? amountInput(service.price.amount_minor, currency, locale) : "");
  const [who, setWho] = React.useState<"all" | "some">(service?.staff ?? "all");
  const [some, setSome] = React.useState<string[]>(service?.staff_ids ?? []);
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [refusal, setRefusal] = React.useState<{ code: string; field: string } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const parsed = parseAmount(amount, currency);
  const decimals = minorDigits(currency) > 0;
  const price: Price | null = kind !== "amount" ? { kind } : parsed.kind === "ok" ? { kind, amount_minor: parsed.minor } : null;
  const needsCurrency = unset && kind === "amount" && !chosen;
  const ready = name.trim() !== "" && price !== null && !needsCurrency && (who === "all" || some.length > 0);
  const base = React.useId();

  // Only what changed (5.3); a new service sends everything.
  const changes: ServicePatch = {};
  if (service) {
    if (duration !== service.duration_minutes) changes.duration_minutes = duration;
    if (price && !samePrice(price, service.price)) changes.price = price;
    if ((category.trim() || null) !== (service.category ?? null)) changes.category = category.trim() || null;
    const staffNow = who === "all" ? null : some;
    const staffWas = service.staff === "all" ? null : service.staff_ids;
    if (JSON.stringify(staffNow) !== JSON.stringify(staffWas)) changes.staff_ids = staffNow;
  }
  const dirty = service ? Object.keys(changes).length > 0 || (kind === "amount" && price === null) : name.trim() !== "" || category.trim() !== "" || amount.trim() !== "" || kind !== "none";
  const guard = useDiscardGuard(dirty, onClose);

  const fieldError = (field: string) =>
    refusal?.field === field && SERVICE_ERRORS.has(refusal.code) ? t(`business.services.error.${refusal.code}` as MessageKey) : null;
  const amountError =
    kind !== "amount"
      ? null
      : parsed.kind === "invalid"
        ? parsed.code === "amount_too_large"
          ? t("business.services.error.amount_too_large")
          : t(decimals ? "reservas.svc.price.invalid.decimals" : "reservas.svc.price.invalid")
        : touched && parsed.kind === "empty"
          ? t("business.services.error.price_amount_required")
          : fieldError("price");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    setError(null);
    setRefusal(null);
    if (!ready || !price) return;
    if (service && Object.keys(changes).length === 0) return onClose();
    setBusy(true);
    const currencyChoice = unset && kind === "amount" ? { price_currency: chosen } : {};
    try {
      const res = service
        ? await updateServiceAction({ id: service.id, ...changes, ...(changes.price ? currencyChoice : {}) })
        : await (() => {
            const body = {
              name: name.trim(),
              duration_minutes: duration,
              price,
              staff_ids: who === "all" ? null : some,
              category: category.trim() || null,
              ...currencyChoice,
            };
            return createServiceAction({ ...body, idempotencyKey: key.take(body) });
          })();
      if (res.ok) {
        key.done();
        toast.success(t("reservas.settings.saved"));
        refresh();
        onClose();
        return;
      }
      const field = typeof res.info?.field === "string" ? res.info.field : "";
      if (res.status === 422 && res.code && SERVICE_ERRORS.has(res.code) && ["price", "duration_min", "category", "name"].includes(field)) {
        setRefusal({ code: res.code, field });
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
    <>
      <Dialog open onOpenChange={guard.onOpenChange}>
        <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
          <form onSubmit={save} className="grid gap-4" noValidate>
            <DialogHeader>
              <DialogTitle>{service ? t("reservas.svc.edit") : t("reservas.svc.add")}</DialogTitle>
            </DialogHeader>
            <Field
              label={t("reservas.svc.name")}
              required={!service}
              requiredLabel={t("reservas.required")}
              hint={service ? t("business.services.name.fixed") : undefined}
              error={touched && !name.trim() ? t("reservas.form.nameRequired") : fieldError("name")}
            >
              {(a11y) => (
                <Input
                  {...a11y}
                  value={name}
                  readOnly={!!service}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={service ? undefined : t("reservas.svc.name.placeholder")}
                  maxLength={NAME_MAX}
                />
              )}
            </Field>
            <Field label={t("reservas.svc.category")} optionalLabel={t("reservas.optional")} hint={t("reservas.svc.category.hint")} error={fieldError("category")}>
              {(a11y) => (
                <>
                  <Input {...a11y} value={category} maxLength={CATEGORY_MAX} list={`${base}-categories`} autoComplete="off" onChange={(e) => (setCategory(e.target.value), setRefusal(null))} />
                  <datalist id={`${base}-categories`}>
                    {categories.map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </>
              )}
            </Field>
            <Field label={t("reservas.svc.duration")} error={fieldError("duration_min")}>
              {(a11y) => (
                <NativeSelect {...a11y} value={duration} onChange={(e) => (setDuration(Number(e.target.value)), setRefusal(null))} wrapperClassName="w-full sm:w-48">
                  {DURATIONS.map((m) => (
                    <option key={m} value={m}>
                      {formatMinutes(m)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </Field>
            <fieldset className="grid min-w-0 gap-2">
              <legend className="mb-2 text-sm font-medium">{t("reservas.svc.price")}</legend>
              <div className="flex min-w-0 flex-wrap gap-x-4 gap-y-2">
                {PRICE_KINDS.map((k) => (
                  <label key={k} className="flex min-h-6 items-center gap-2 text-sm">
                    <input type="radio" name={`${base}-price`} checked={kind === k} onChange={() => (setKind(k), setRefusal(null))} className="size-4 accent-primary" />
                    {t(`business.services.price.${k}` as MessageKey)}
                  </label>
                ))}
              </div>
              {kind === "none" ? <p className="text-xs text-pretty text-muted-foreground">{t("business.services.price.none.hint")}</p> : null}
              {kind === "amount" ? (
                <Field
                  label={t("business.services.price.amount")}
                  hint={unset && !chosen ? undefined : t("reservas.svc.price.amount.hint", { currency })}
                  error={amountError}
                >
                  {(a11y) => (
                    <Input
                      {...a11y}
                      inputMode="decimal"
                      value={amount}
                      onChange={(e) => (setAmount(e.target.value), setRefusal(null))}
                      placeholder={decimals ? (locale === "en" ? "15.50" : "15,50") : "15000"}
                      maxLength={20}
                      className="max-w-48"
                    />
                  )}
                </Field>
              ) : null}
            </fieldset>
            {unset && kind === "amount" ? (
              <Field
                label={t("reservas.svc.currency")}
                required
                requiredLabel={t("reservas.required")}
                hint={t("reservas.svc.currency.hint")}
                error={touched && !chosen ? t("reservas.svc.currency.required") : null}
              >
                {(a11y) => (
                  <NativeSelect {...a11y} value={chosen} onChange={(e) => setChosen(e.target.value)} wrapperClassName="w-full">
                    <option value="">{t("reservas.svc.currency.choose")}</option>
                    {currencyOptions(null).map((c) => (
                      <option key={c} value={c}>
                        {`${c} · ${displayName(locale, "currency", c)}`}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </Field>
            ) : null}
            <fieldset className="grid gap-2">
              <legend className="mb-2 text-sm font-medium">{t("reservas.svc.who")}</legend>
              <label className="flex items-center gap-3 text-sm">
                <input type="radio" name={`${base}-who`} checked={who === "all"} onChange={() => setWho("all")} className="size-4 accent-primary" />
                {t("reservas.svc.who.all")}
              </label>
              <label className="flex items-center gap-3 text-sm">
                <input type="radio" name={`${base}-who`} checked={who === "some"} onChange={() => setWho("some")} className="size-4 accent-primary" />
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
              <Button type="button" variant="outline" onClick={guard.close}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={busy} disabled={!ready && touched}>
                {t("reservas.settings.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {guard.dialog}
    </>
  );
}
