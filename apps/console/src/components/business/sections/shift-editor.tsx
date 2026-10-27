"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { MAX_SHIFTS, isOvernight, newKey, type DraftShift } from "./hours-model";

const DASH = "–";

/** «09:00–14:00» y, si cierra al día siguiente, su rótulo. */
export function ShiftText({ open, close }: { open: string; close: string }) {
  const t = useT();
  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-x-2">
      <span className="tabular-nums">{`${open}${DASH}${close}`}</span>
      {isOvernight(open, close) ? <span className="text-xs text-muted-foreground">{t("business.hours.overnight")}</span> : null}
    </span>
  );
}

/**
 * Los turnos de un día (o de un bloque): abrir y cerrar, «Nocturno · cierra al
 * día siguiente» cuando el cierre es igual o anterior a la apertura, añadir
 * hasta {@link MAX_SHIFTS} y quitar. Sin turnos, el día está cerrado.
 */
export function ShiftEditor({
  legend,
  shifts,
  onChange,
  canWrite,
}: {
  legend: string;
  shifts: DraftShift[];
  onChange: (next: DraftShift[]) => void;
  canWrite: boolean;
}) {
  const t = useT();
  const base = React.useId();
  const full = shifts.length >= MAX_SHIFTS;

  function update(i: number, patch: Partial<DraftShift>) {
    onChange(shifts.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  }

  return (
    <fieldset className="grid min-w-0 gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
      <legend className="float-left mb-1 text-sm font-medium">{legend}</legend>
      <div className="clear-left grid min-w-0 gap-2">
        {shifts.length === 0 ? <p className="text-sm text-muted-foreground">{t("business.hours.closed")}</p> : null}
        {canWrite
          ? shifts.map((s, i) => {
              const n = i + 1;
              const openId = `${base}-${s.key}-open`;
              const closeId = `${base}-${s.key}-close`;
              return (
                <div key={s.key} className="flex min-w-0 flex-wrap items-center gap-2">
                  <label htmlFor={openId} className="sr-only">
                    {t("business.hours.open", { n })}
                  </label>
                  <Input
                    id={openId}
                    type="time"
                    step={300}
                    value={s.open}
                    onChange={(e) => update(i, { open: e.target.value })}
                    className="w-28"
                  />
                  <span aria-hidden="true">{DASH}</span>
                  <label htmlFor={closeId} className="sr-only">
                    {t("business.hours.close", { n })}
                  </label>
                  <Input
                    id={closeId}
                    type="time"
                    step={300}
                    value={s.close === "24:00" ? "00:00" : s.close}
                    onChange={(e) => update(i, { close: e.target.value })}
                    className="w-28"
                  />
                  {isOvernight(s.open, s.close) ? (
                    <span className="text-xs text-muted-foreground">{t("business.hours.overnight")}</span>
                  ) : null}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t("business.hours.remove_shift", { n })}
                    onClick={() => onChange(shifts.filter((_, j) => j !== i))}
                  >
                    <X aria-hidden="true" />
                  </Button>
                </div>
              );
            })
          : shifts.map((s) => (
              <p key={s.key} className="text-sm">
                <ShiftText open={s.open} close={s.close} />
              </p>
            ))}
        {canWrite ? (
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={full}
              onClick={() => onChange([...shifts, { key: newKey(), open: "09:00", close: "14:00" }])}
            >
              <Plus aria-hidden="true" />
              {t("business.hours.add_shift")}
            </Button>
            {full ? <span className="text-xs text-muted-foreground">{t("business.hours.max_shifts")}</span> : null}
          </div>
        ) : null}
      </div>
    </fieldset>
  );
}
