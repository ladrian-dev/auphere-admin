"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, EmptyState, Field, Input, NativeSelect } from "@nexus/ui";

import { archiveSpecialDateAction, createSpecialDateAction } from "@/app/(console)/clients/[ref]/business/actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Location, SpecialDate, SpecialDateBody, SpecialDates } from "@/lib/backend/business-sections";

import type { DraftShift } from "./hours-model";
import { ConflictNotice, SectionFrame, problemOf, type Result } from "./section-frame";
import { ShiftEditor, ShiftText } from "./shift-editor";

type Act<B> = (body: B) => Promise<Result<SpecialDates>>;
export type SpecialDatesActions = {
  create: Act<{ ref: string; revision: number; body: SpecialDateBody }>;
  archive: Act<{ ref: string; revision: number; id: string }>;
};

const SERVER_ACTIONS: SpecialDatesActions = {
  create: (b) => createSpecialDateAction(b),
  archive: (b) => archiveSpecialDateAction(b),
};

function formatDate(iso: string, locale: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)),
  );
}

/** Hoy (`AAAA-MM-DD`) en la zona del negocio; sin zona, la del navegador. */
export function todayIn(timezone?: string | null): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: timezone || undefined, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  }
}

/**
 * «Fechas especiales» de Negocio (spec 047, T060; requisito 10.3): cerrado o
 * con turnos propios, de un día o de un rango, con nombre, del negocio o de una
 * sede. La usan el agente, «¿abierto ahora?» y los huecos de Reservas.
 *
 * Spec 056: una fecha cuyo «Hasta» ya pasó no se guarda (11.4, D10), con el
 * «hoy» de la zona del negocio, como la API; y quitar una pide confirmación (12.1).
 */
export function SpecialDatesSection({
  refId,
  specialDates: initial,
  locations,
  canWrite,
  actions = SERVER_ACTIONS,
  nested = false,
  timezone,
  today: todayProp,
}: {
  refId: string;
  specialDates: SpecialDates;
  locations: readonly Location[];
  canWrite: boolean;
  actions?: SpecialDatesActions;
  /** Dentro de la tarjeta de Horarios: el prototipo no tiene sección propia. */
  nested?: boolean;
  /** La zona del negocio, para saber qué día es hoy allí. */
  timezone?: string | null;
  /** Hoy (`AAAA-MM-DD`), para las pruebas; si no, el de `timezone`. */
  today?: string;
}) {
  const t = useT();
  const locale = useLocale();
  const [dates, setDates] = React.useState(initial);
  const [adding, setAdding] = React.useState(false);
  const [conflict, setConflict] = React.useState(false);
  const [removing, setRemoving] = React.useState<SpecialDate | null>(null);
  const [pending, startTransition] = React.useTransition();
  const today = todayProp ?? todayIn(timezone);
  const where = (id: string | null) => locations.find((l) => l.id === id)?.name ?? t("business.special.location.all");
  const when = (d: SpecialDate) => (d.from === d.to ? formatDate(d.from, locale) : `${formatDate(d.from, locale)} – ${formatDate(d.to, locale)}`);

  async function apply(res: Result<SpecialDates>): Promise<string | null> {
    if (res.ok) {
      setDates(res.data);
      setConflict(false);
      toast.success(t("business.section.saved"));
      return null;
    }
    const code = problemOf(res);
    if (code === "conflict") setConflict(true);
    return code;
  }

  return (
    <SectionFrame id="business-special-dates" title={t("business.special.title")} state={nested ? null : dates.state} canWrite={canWrite} nested={nested}>
      <div className="grid min-w-0 gap-4">
        {conflict ? <ConflictNotice /> : null}
        {dates.items.length === 0 ? (
          <EmptyState title={t("business.special.empty")} readonly />
        ) : (
          <ul className="grid min-w-0 gap-2">
            {dates.items.map((d) => (
              <li key={d.id} className="flex min-w-0 flex-wrap items-start justify-between gap-3 rounded-md border border-border p-3">
                <div className="grid min-w-0 flex-1 basis-56 gap-1">
                  <p className="font-medium text-pretty break-words">
                    <span className="tabular-nums">{when(d)}</span>
                    {d.name ? ` · ${d.name}` : ""}
                  </p>
                  <p className="text-sm">
                    {d.closed ? (
                      t("business.hours.closed")
                    ) : (
                      <span className="inline-flex min-w-0 flex-wrap gap-x-3">
                        {d.shifts.map((s) => (
                          <ShiftText key={`${s.open}-${s.close}`} open={s.open} close={s.close} />
                        ))}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">{where(d.location_id)}</p>
                </div>
                {canWrite ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={pending}
                    aria-label={t("business.special.remove", { name: d.name || when(d) })}
                    onClick={() => setRemoving(d)}
                  >
                    <X aria-hidden="true" />
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canWrite && !adding ? (
          <div>
            <Button type="button" variant="outline" onClick={() => setAdding(true)}>
              <Plus aria-hidden="true" />
              {t("business.special.add")}
            </Button>
          </div>
        ) : null}
        {adding ? (
          <SpecialDateForm
            today={today}
            locations={locations.filter((l) => !l.archived)}
            onCancel={() => setAdding(false)}
            onSave={async (body) => {
              const problem = await apply(await actions.create({ ref: refId, revision: dates.revision, body }));
              if (problem === null || problem === "conflict") setAdding(false);
              return problem;
            }}
          />
        ) : null}
      </div>
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => (open ? undefined : setRemoving(null))}
        title={removing ? t("business.special.remove.title", { name: removing.name || when(removing) }) : ""}
        description={t("business.special.remove.body")}
        confirmLabel={t("business.special.remove.confirm")}
        cancelLabel={t("business.section.cancel")}
        destructive
        onConfirm={() => {
          const target = removing;
          setRemoving(null);
          if (target) startTransition(async () => void (await apply(await actions.archive({ ref: refId, revision: dates.revision, id: target.id }))));
        }}
      />
    </SectionFrame>
  );
}

function SpecialDateForm({
  today,
  locations,
  onCancel,
  onSave,
}: {
  today: string;
  locations: readonly Location[];
  onCancel: () => void;
  onSave: (body: SpecialDateBody) => Promise<string | null>;
}) {
  const t = useT();
  const [name, setName] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [closed, setClosed] = React.useState(true);
  const [shifts, setShifts] = React.useState<DraftShift[]>([]);
  const [locationId, setLocationId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const base = React.useId();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const end = to || from;
    if (!from) return setError("no_from");
    if (end < from) return setError("date_range");
    if (end < today) return setError("date_past");
    if (!closed && shifts.length === 0) return setError("no_shifts");
    startTransition(async () => {
      const problem = await onSave({
        name: name.trim() || null,
        location_id: locationId || null,
        from,
        to: end,
        closed,
        shifts: closed ? [] : shifts.map((s) => ({ open: s.open, close: s.close })),
      });
      if (problem && problem !== "conflict") setError(["date_range", "no_shifts", "date_past"].includes(problem) ? problem : "generic");
    });
  }

  return (
    <form onSubmit={submit} className="grid min-w-0 gap-3 rounded-md border border-border p-3" noValidate>
      <div className="grid min-w-0 gap-3 sm:grid-cols-3">
        <Field label={t("business.special.name")}>
          {(a11y) => <Input {...a11y} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label={t("business.special.from")} required>
          {(a11y) => <Input {...a11y} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}
        </Field>
        <Field label={t("business.special.to")}>
          {(a11y) => <Input {...a11y} type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />}
        </Field>
      </div>
      {locations.length ? (
        <div className="grid gap-2 sm:max-w-sm">
          <label htmlFor={`${base}-where`} className="text-sm font-medium">
            {t("business.special.location")}
          </label>
          <NativeSelect id={`${base}-where`} value={locationId} onChange={(e) => setLocationId(e.target.value)}>
            <option value="">{t("business.special.location.all")}</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      ) : null}
      <label className="flex min-h-6 items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-primary" checked={closed} onChange={(e) => setClosed(e.target.checked)} />
        {t("business.special.closed")}
      </label>
      {!closed ? <ShiftEditor legend={t("business.hours.title")} shifts={shifts} onChange={setShifts} canWrite /> : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error === "generic" ? t("business.section.error.generic") : t(`business.special.error.${error}` as MessageKey)}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending}>
          {t("business.special.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("business.section.cancel")}
        </Button>
      </div>
    </form>
  );
}
