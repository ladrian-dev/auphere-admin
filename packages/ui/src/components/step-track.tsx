import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type Step = {
  key: string;
  label: ReactNode;
  /** Partes hechas de este paso. */
  done: number;
  /** De cuántas partes consta. Es también su peso en el ancho: un paso con
   *  más partes ocupa más, que es lo que enseña cuál cuesta más. */
  of: number;
  /** Lo que se sabe de él: «versión 1», «+34 600…», «50.000 créditos». */
  detail?: ReactNode;
  /** El que toca ahora. Solo puede haber uno. */
  current?: boolean;
};

type StepTrackProps = {
  steps: Step[];
  ariaLabel: string;
  /** La frase que lo resume para quien no ve las barras. */
  summary: string;
  className?: string;
};

/**
 * El recorrido de un alta, paso a paso, con **cuánto** lleva hecho cada uno.
 *
 * `Stepper` dice en cuál estás; esto dice cuánto te queda **dentro** de cada
 * uno. Nace de un problema real: cuatro palomas verdes decían «hecho / no
 * hecho» y escondían que «Agente» son dos cosas (escribirlo y publicarlo) y
 * «Activación» una sola. El partner no podía saber cuál le iba a costar.
 *
 * Tres decisiones que lo sostienen:
 *
 * - **El ancho lo da el número de partes, no la estética.** Un paso de dos
 *   partes ocupa el doble que uno de una. Así la barra enseña dónde está el
 *   trabajo sin que nadie tenga que afirmar cuánto tarda cada cosa, que es
 *   un dato que no tenemos.
 * - **El estado está en texto, no solo en la barra.** Cada paso lleva su
 *   detalle debajo y el conjunto su frase de resumen: quien no distingue el
 *   relleno lee lo mismo.
 * - **Sin ordinales ni línea de unión.** Los pasos se pueden hacer en
 *   cualquier orden, y ambos son la gramática de una secuencia.
 */
function StepTrack({ steps, ariaLabel, summary, className }: StepTrackProps) {
  return (
    <div
      data-slot="step-track"
      role="group"
      aria-label={ariaLabel}
      className={cn("flex min-w-0 flex-wrap gap-x-(--space-block) gap-y-3", className)}
    >
      {steps.map((s) => {
        const pct = s.of > 0 ? Math.min(100, Math.max(0, (s.done / s.of) * 100)) : 0;
        const state = s.done >= s.of ? "done" : s.done > 0 ? "partial" : "todo";
        return (
          <div
            key={s.key}
            data-state={state}
            // El peso: un paso de dos partes ocupa el doble de ancho.
            style={{ flexGrow: s.of, flexBasis: `${s.of * 5}rem` }}
            className="flex min-w-0 flex-col gap-2"
            {...(s.current ? { "aria-current": "step" as const } : {})}
          >
            <span
              className={cn(
                "truncate text-sm",
                state === "todo" ? "text-muted-foreground" : "font-medium text-foreground",
              )}
            >
              {s.label}
            </span>
            <span className="h-2 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
              <span
                className={cn(
                  "block h-full rounded-full transition-[width] duration-(--duration-slow)",
                  state === "done" ? "bg-primary" : "bg-primary/60",
                )}
                style={{ width: `${pct}%` }}
              />
            </span>
            {s.detail ? <span className="truncate text-xs text-muted-foreground">{s.detail}</span> : null}
          </div>
        );
      })}
      <span className="sr-only">{summary}</span>
    </div>
  );
}

export { StepTrack, type StepTrackProps };
