import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type Step = {
  key: string;
  label: ReactNode;
  /** Partes hechas de este paso. */
  done: number;
  /** De cuántas partes consta: da el relleno parcial de la barra. **No** da
   *  el ancho — todas las barras miden igual. Anchos distintos hacían que
   *  el ojo contara pasos de distinto tamaño y el contador no cuadrara. */
  of: number;
  /** Lo que se sabe de él: «versión 1», «+34 600…», «50.000 créditos». */
  detail?: ReactNode;
  /** El que toca ahora. Solo puede haber uno. */
  current?: boolean;
  /** Dónde se resuelve. Convierte la etiqueta del paso pendiente en el
   *  enlace que lleva allí, en vez de un botón suelto debajo. */
  href?: string;
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
 * - **Todas las barras miden igual.** Un primer intento las ensanchó según
 *   sus partes, y el resultado fue ilegible: tres barras de anchos
 *   distintos sobre un contador que decía «4 de 5» — el ojo cuenta barras,
 *   así que el contador tiene que contar lo mismo.
 * - **El paso pendiente lleva su enlace.** La flecha en su etiqueta dice
 *   dónde se resuelve, en el sitio donde estás mirando el problema, en vez
 *   de un botón al pie de la tarjeta.
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
            className="flex min-w-0 flex-1 basis-40 flex-col gap-2"
            {...(s.current ? { "aria-current": "step" as const } : {})}
          >
            {s.href ? (
              <a
                href={s.href}
                className={cn(
                  "inline-flex min-w-0 items-center gap-1 text-sm underline-offset-4 hover:underline",
                  state === "todo" ? "text-foreground" : "font-medium text-foreground",
                )}
              >
                <span className="truncate">{s.label}</span>
                <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
              </a>
            ) : (
              <span
                className={cn(
                  "truncate text-sm",
                  state === "todo" ? "text-muted-foreground" : "font-medium text-foreground",
                )}
              >
                {s.label}
              </span>
            )}
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
