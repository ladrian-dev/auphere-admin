"use client";

import { Printer } from "lucide-react";
import * as React from "react";

import { Button, Input, NativeSelect, SegmentedControl } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

import { REPORT_MAX_DAYS, REPORT_PRESETS, addDays, lastDays, periodProblem, presetOf, type Period, type PeriodProblem } from "./report-model";

export type ReportClientOption = { ref: string; name: string };

const PROBLEM_TEXT: Record<PeriodProblem, MessageKey> = {
  range_reversed: "report.filter.order",
  range_in_future: "report.filter.order",
  range_too_long: "report.filter.tooLong",
  invalid: "report.filter.invalid",
};

/**
 * Spec 083 (requisito 1.2): los dos filtros del informe, el cliente y el periodo,
 * y «Imprimir», la única acción principal. Cada cambio va a la dirección (1.3):
 * otro cliente lleva a su informe con las mismas fechas. Las fechas no dejan pedir
 * lo que la API rechazaría (1.5): `min` y `max` acotan el calendario y, si se
 * escribe a mano algo imposible, se dice y no se pide. No se imprime.
 */
export function ReportFilters({
  refId,
  clientName,
  clients,
  period,
  today,
  onGo,
  onPrint,
}: {
  refId: string;
  clientName: string;
  clients: ReportClientOption[];
  period: Period;
  today: string;
  onGo: (ref: string, period: Period) => void;
  onPrint: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [draft, setDraft] = React.useState<Period>(period);
  const [problem, setProblem] = React.useState<PeriodProblem | null>(null);
  const errorId = React.useId();
  const options = clients.some((c) => c.ref === refId) ? clients : [{ ref: refId, name: clientName }, ...clients];
  const preset = presetOf(period, today);
  const lang = locale === "es" ? "es-ES" : "en-GB";

  function change(next: Period) {
    setDraft(next);
    const found = periodProblem(next, today);
    setProblem(found);
    if (found === null) onGo(refId, next);
  }

  const latestTo = addDays(draft.from, REPORT_MAX_DAYS - 1) < today ? addDays(draft.from, REPORT_MAX_DAYS - 1) : today;
  const latestFrom = draft.to < today ? draft.to : today;

  return (
    <div role="group" aria-label={t("report.filters")} data-slot="report-filters" className="grid min-w-0 gap-2 print:hidden">
      <div className="flex min-w-0 flex-wrap items-end gap-3">
        <label className="grid w-full min-w-0 gap-1 text-sm font-medium sm:w-auto">
          {t("report.filter.client")}
          <NativeSelect wrapperClassName="w-full sm:w-64" value={refId} onChange={(e) => onGo(e.target.value, period)}>
            {options.map((c) => (
              <option key={c.ref} value={c.ref}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        {/* `min-w-36`: a 360 px los atajos comparten fila y, con `min-w-0`, las fechas se quedaban en el icono. */}
        <label className="grid min-w-36 flex-1 gap-1 text-sm font-medium sm:flex-none">
          {t("report.filter.from")}
          <Input
            type="date"
            lang={lang}
            value={draft.from}
            min={addDays(draft.to, -(REPORT_MAX_DAYS - 1))}
            max={latestFrom}
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? errorId : undefined}
            onChange={(e) => change({ from: e.target.value, to: draft.to })}
            className="sm:w-40"
          />
        </label>
        <label className="grid min-w-36 flex-1 gap-1 text-sm font-medium sm:flex-none">
          {t("report.filter.to")}
          <Input
            type="date"
            lang={lang}
            value={draft.to}
            min={draft.from}
            max={latestTo}
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? errorId : undefined}
            onChange={(e) => change({ from: draft.from, to: e.target.value })}
            className="sm:w-40"
          />
        </label>
        <SegmentedControl
          type="pressed"
          aria-label={t("report.filter.presets")}
          value={preset === null ? "" : String(preset)}
          onValueChange={(v) => change(lastDays(Number(v), today))}
          options={REPORT_PRESETS.map((n) => ({ value: String(n), label: t("report.filter.days", { n }) }))}
        />
        <Button type="button" onClick={onPrint} className="sm:ml-auto">
          <Printer aria-hidden="true" />
          {t("report.print")}
        </Button>
      </div>
      {problem ? (
        <p id={errorId} role="alert" className="text-sm text-pretty text-destructive">
          {t(PROBLEM_TEXT[problem])}
        </p>
      ) : null}
    </div>
  );
}
