"use client";

import { StatusBadge } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Day } from "@/lib/backend/business-sections";

import { setRow, type HoursDraft, type Row } from "./hours-model";
import { ShiftEditor } from "./shift-editor";

/**
 * Los turnos de la semana, por filas — spec 056 (requisito 5.1). Puro: recibe
 * el borrador y devuelve el siguiente, sin guardar ni cargar nada. Lo usan:
 *
 * - la ficha del partner (`hours-section.tsx`), con sus filas por bloques o
 *   día por día;
 * - los Ajustes de Reservas del cliente (`reservas/settings/hours-editor.tsx`),
 *   siempre día por día: la API decide si sigue por bloques.
 *
 * Las reglas son las de la API (`lib/business-rules.ts`): de 0 a 6 turnos por
 * día, pasos de 5 minutos y nocturnos rotulados. `review` marca «Revísalo» en
 * los días con una hora guardada fuera del paso (5.5): se enseña tal cual.
 */
export function WeekEditor({
  draft,
  rows,
  editable,
  review = [],
  onChange,
}: {
  draft: HoursDraft;
  rows: readonly Row[];
  editable: boolean;
  review?: readonly Day[];
  onChange: (next: HoursDraft) => void;
}) {
  const t = useT();
  const rowName = (row: Row) => (row.key === "weekdays" ? t("business.hours.row.weekdays") : t(`business.hours.day.${row.key}` as MessageKey));
  return (
    <div className="grid min-w-0 gap-3">
      {rows.map((row) => (
        <ShiftEditor
          key={row.key}
          legend={rowName(row)}
          shifts={draft.days[row.days[0] as Day]}
          canWrite={editable}
          note={
            row.days.some((d) => review.includes(d)) ? (
              <StatusBadge tone="warning" title={t("business.hours.review.hint")}>
                {t("business.hours.review")}
              </StatusBadge>
            ) : null
          }
          onChange={(next) => onChange(setRow(draft, row, next))}
        />
      ))}
    </div>
  );
}
