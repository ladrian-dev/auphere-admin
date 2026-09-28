"use client";

import { Plus, X } from "lucide-react";
import * as React from "react";

import { Button, Input } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { DAYS, dayName, summarise, type Hours, type Day } from "./hours";

/**
 * El horario, elegido (spec 019, R7).
 *
 * Tres decisiones del owner (2026-09-28), y cada una corrige algo concreto:
 *
 * - **Día a día primero.** El resumido parecía más amable pero mentía por
 *   omisión: casi ningún negocio abre los siete días igual, así que empezar
 *   por «de lunes a viernes» obliga a descubrir dónde se corrige.
 * - **Un día cerrado se quita, no se apaga.** La «X» lo saca y deja un «+»
 *   para volver a ponerlo. Un interruptor «Abre / Cerrado» con dos horas al
 *   lado que ya no significan nada es una fila que se contradice.
 * - **No hay campo «Sábados».** Existía porque el horario era texto libre y
 *   los sábados no cabían en la cadena. Aquí el sábado es un día más.
 */
export function HoursField({ value, onChange }: { value: Hours; onChange: (h: Hours) => void }) {
  const t = useT();
  const [resumido, setResumido] = React.useState(false);

  function set(day: Day, slot: Hours[Day]) {
    onChange({ ...value, [day]: slot });
  }

  // El primero que abra da el tramo del modo resumido: resumir no puede
  // abrir un día cerrado, así que tampoco puede inventarse una hora.
  const primero = DAYS.map((d) => value[d]).find((s) => s !== null) ?? { from: "10:00", to: "19:00" };

  return (
    <fieldset className="flex min-w-0 flex-col gap-3">
      <legend className="text-sm font-medium">{t("wizard.hours.legend")}</legend>

      {resumido ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-32 shrink-0 text-sm">{t("wizard.hours.everyDay")}</span>
          <Input
            type="time"
            value={primero.from}
            aria-label={t("wizard.hours.opens")}
            className="w-32"
            onChange={(e) => onChange(summarise(value, { ...primero, from: e.target.value }))}
          />
          <span className="text-sm text-muted-foreground">{t("wizard.hours.to")}</span>
          <Input
            type="time"
            value={primero.to}
            aria-label={t("wizard.hours.closes")}
            className="w-32"
            onChange={(e) => onChange(summarise(value, { ...primero, to: e.target.value }))}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {DAYS.map((day) => {
            const slot = value[day];
            const nombre = dayName(day);
            return (
              <div key={day} className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="w-24 shrink-0 text-sm">{nombre}</span>
                {slot ? (
                  <>
                    <Input
                      type="time"
                      value={slot.from}
                      aria-label={t("wizard.hours.dayOpens", { day: nombre })}
                      className="w-32"
                      onChange={(e) => set(day, { ...slot, from: e.target.value })}
                    />
                    <span className="text-sm text-muted-foreground">{t("wizard.hours.to")}</span>
                    <Input
                      type="time"
                      value={slot.to}
                      aria-label={t("wizard.hours.dayCloses", { day: nombre })}
                      className="w-32"
                      onChange={(e) => set(day, { ...slot, to: e.target.value })}
                    />
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label={t("wizard.hours.close", { day: nombre })}
                      onClick={() => set(day, null)}
                    >
                      <X aria-hidden="true" />
                    </Button>
                  </>
                ) : (
                  <>
                    <span className="text-sm text-muted-foreground">{t("wizard.hours.closed")}</span>
                    <Button
                      size="icon-sm"
                      variant="outline"
                      aria-label={t("wizard.hours.open", { day: nombre })}
                      onClick={() => set(day, { ...primero })}
                    >
                      <Plus aria-hidden="true" />
                    </Button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      <button
        type="button"
        onClick={() => setResumido((v) => !v)}
        aria-expanded={!resumido}
        className="self-start text-sm text-muted-foreground underline underline-offset-4"
      >
        {resumido ? t("wizard.hours.perDay") : t("wizard.hours.allSame")}
      </button>
    </fieldset>
  );
}
