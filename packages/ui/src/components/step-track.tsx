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
  /** Dónde se resuelve. El enlace va en la línea del detalle —el mismo
   *  sitio donde los pasos hechos dicen «v1» o «50.000»—, de modo que esa
   *  línea contesta siempre lo mismo: qué hay, o qué falta hacer. */
  href?: string;
  /** El texto del enlace: «Conectar canal», «Asignar crédito». */
  hrefLabel?: ReactNode;
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
 * - **El paso pendiente lleva su enlace donde los demás llevan su dato.**
 *   La línea de debajo de la barra dice «v1» o «50.000» cuando el paso está
 *   hecho y «Conectar canal» cuando falta: una sola línea que siempre
 *   contesta lo mismo, en vez de un botón al pie de la tarjeta.
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
            <span
              className={cn(
                "truncate text-sm",
                state === "todo" ? "opacity-80" : "font-medium",
              )}
            >
              {s.label}
            </span>
            {/* La pista se tiñe del color del texto: así el componente sirve
                igual sobre una tarjeta blanca que sobre el verde oscuro, sin
                saber en cuál está. */}
            <span className="h-2 w-full overflow-hidden rounded-full bg-current/15" aria-hidden="true">
              <span
                className={cn(
                  "block h-full rounded-full transition-[width] duration-(--duration-slow)",
                  state === "done" ? "bg-mountain-meadow" : "bg-mountain-meadow/60",
                )}
                style={{ width: `${pct}%` }}
              />
            </span>
            {s.href ? (
              <a href={s.href} className="truncate text-xs underline underline-offset-4 hover:no-underline">
                {s.hrefLabel ?? s.label}
              </a>
            ) : s.detail ? (
              <span className="truncate text-xs opacity-75">{s.detail}</span>
            ) : null}
          </div>
        );
      })}
      <span className="sr-only">{summary}</span>
    </div>
  );
}

export { StepTrack, type StepTrackProps };
