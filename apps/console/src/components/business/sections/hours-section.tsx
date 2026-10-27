"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, NativeSelect } from "@nexus/ui";

import { loadHoursAction, saveHoursAction } from "@/app/(console)/clients/[ref]/business/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Day, Hours, HoursBody, Layout, Location } from "@/lib/backend/business-sections";

import { blockRows, blocksLoss, bodyFromDraft, draftFromHours, setRow, toBlocks, validateDraft, type HoursDraft, type Row } from "./hours-model";
import { ConflictNotice, SectionFrame, problemOf, type Result } from "./section-frame";
import { ShiftEditor } from "./shift-editor";

type Save = (body: { ref: string; revision: number; locationId: string | null; body: HoursBody }) => Promise<Result<Hours>>;
type Load = (body: { ref: string; locationId: string | null }) => Promise<Result<Hours>>;

const ERRORS = new Set(["too_many_shifts", "overlap", "overlap_next_day", "invalid_time"]);

/**
 * «Horario» de Negocio (spec 047, T060; requisito 10, historia 5): el del
 * negocio o el propio de una sede, por bloques o día por día, con hasta 6
 * turnos, los nocturnos rotulados y la frase «Así lo dirá el agente» que
 * devuelve la API al guardar. Pasar a bloques con días distintos pide
 * confirmación diciendo qué se pierde (10.6).
 */
export function HoursSection({
  refId,
  hours: initial,
  locations,
  canWrite,
  save = (b) => saveHoursAction(b),
  load = (b) => loadHoursAction(b),
}: {
  refId: string;
  hours: Hours;
  locations: readonly Location[];
  canWrite: boolean;
  save?: Save;
  load?: Load;
}) {
  const t = useT();
  const [hours, setHours] = React.useState(initial);
  const [draft, setDraft] = React.useState<HoursDraft>(() => draftFromHours(initial));
  const [inherit, setInherit] = React.useState(initial.inherits);
  const [dirty, setDirty] = React.useState(false);
  const [lost, setLost] = React.useState<Day[] | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const base = React.useId();
  const editable = canWrite && !inherit;
  const live = locations.filter((l) => !l.archived);
  const dayName = (d: Day) => t(`business.hours.day.${d}` as MessageKey);
  const rowName = (row: Row) => (row.key === "weekdays" ? t("business.hours.row.weekdays") : dayName(row.key));

  function reset(next: Hours) {
    setHours(next);
    setDraft(draftFromHours(next));
    setInherit(next.inherits);
    setDirty(false);
    setProblem(null);
  }

  function edit(next: HoursDraft) {
    setDraft(next);
    setDirty(true);
    setProblem(null);
  }

  function chooseLayout(layout: Layout) {
    if (layout === draft.layout) return;
    if (layout === "daily") return edit({ ...draft, layout });
    const loss = blocksLoss(draft);
    if (loss.length) setLost(loss);
    else edit(toBlocks(draft));
  }

  function switchLocation(value: string) {
    const locationId = value || null;
    startTransition(async () => {
      const res = await load({ ref: refId, locationId });
      if (res.ok) reset(res.data);
      else toast.error(t("business.section.error"));
    });
  }

  function submit(confirmLoss = false) {
    const problems = validateDraft(draft);
    if (!inherit && problems.length) {
      const first = problems[0];
      if (first) setProblem(t(`business.hours.error.${first.code}` as MessageKey, { day: dayName(first.day) }));
      return;
    }
    const body: HoursBody = inherit ? { inherit: true } : bodyFromDraft(draft, { confirmLoss });
    startTransition(async () => {
      const res = await save({ ref: refId, revision: hours.revision, locationId: hours.location_id, body });
      if (res.ok) {
        reset(res.data);
        toast.success(t("business.section.saved"));
        return;
      }
      const code = problemOf(res);
      if (res.status === 409 && res.code === "blocks_lose_days") {
        setLost((res.info?.lost as Day[] | undefined) ?? blocksLoss(draft));
      } else if (code === "conflict") {
        setProblem("conflict");
      } else if (ERRORS.has(code)) {
        const day = typeof res.info?.day === "string" ? dayName(res.info.day as Day) : "";
        setProblem(t(`business.hours.error.${code}` as MessageKey, { day }));
      } else {
        setProblem(t("business.section.error.generic"));
      }
    });
  }

  const shown = inherit ? draftFromHours(hours) : draft;
  const label = dirty ? null : hours.label;

  return (
    <SectionFrame id="business-hours" title={t("business.hours.title")} intro={t("business.hours.intro")} state={hours.state} canWrite={canWrite}>
      <div className="grid min-w-0 gap-4">
        {live.length > 0 ? (
          <div className="grid min-w-0 gap-2 sm:max-w-sm">
            <label htmlFor={`${base}-of`} className="text-sm font-medium">
              {t("business.hours.of")}
            </label>
            <NativeSelect id={`${base}-of`} value={hours.location_id ?? ""} onChange={(e) => switchLocation(e.target.value)} disabled={pending}>
              <option value="">{t("business.hours.of.business")}</option>
              {live.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </NativeSelect>
          </div>
        ) : null}

        {hours.location_id && canWrite ? (
          <label className="flex min-h-6 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={inherit}
              onChange={(e) => {
                setInherit(e.target.checked);
                setDirty(true);
              }}
            />
            {t("business.hours.inherit")}
          </label>
        ) : null}

        {editable ? (
          <fieldset className="grid min-w-0 gap-2">
            <legend className="text-sm font-medium">{t("business.hours.layout")}</legend>
            <div className="flex min-w-0 flex-wrap gap-4">
              {(["blocks", "daily"] as const).map((layout) => (
                <label key={layout} className="flex min-h-6 items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name={`${base}-layout`}
                    className="size-4 accent-primary"
                    checked={draft.layout === layout}
                    onChange={() => chooseLayout(layout)}
                  />
                  {t(`business.hours.layout.${layout}` as MessageKey)}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}

        <div className="grid min-w-0 gap-3">
          {blockRows(shown.layout).map((row) => (
            <ShiftEditor
              key={row.key}
              legend={rowName(row)}
              shifts={shown.days[row.days[0] as Day]}
              canWrite={editable}
              onChange={(next) => edit(setRow(draft, row, next))}
            />
          ))}
        </div>

        <div className="grid min-w-0 gap-1 rounded-md bg-muted/50 p-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{t("business.hours.phrase")}</p>
          <p className="text-sm text-pretty">
            {label ?? (dirty ? t("business.hours.phrase.unsaved") : t("business.hours.phrase.none"))}
          </p>
        </div>

        {problem === "conflict" ? <ConflictNotice onReload={() => switchLocation(hours.location_id ?? "")} /> : null}
        {problem && problem !== "conflict" ? (
          <p role="alert" className="text-sm text-destructive">
            {problem}
          </p>
        ) : null}

        {canWrite ? (
          <div className="flex min-w-0 flex-wrap gap-2">
            <Button type="button" onClick={() => submit()} disabled={pending}>
              {t("business.hours.save")}
            </Button>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={lost !== null}
        onOpenChange={(open) => !open && setLost(null)}
        title={t("business.hours.loss.title")}
        description={t("business.hours.loss.body", { days: (lost ?? []).map((d) => dayName(d).toLowerCase()).join(", ") })}
        confirmLabel={t("business.hours.loss.confirm")}
        cancelLabel={t("business.section.cancel")}
        onConfirm={() => {
          edit(toBlocks(draft));
          setLost(null);
        }}
      />
    </SectionFrame>
  );
}
