import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type StepperProps = {
  steps: { key: string; label: ReactNode }[];
  /** Index of the current step. */
  current: number;
  ariaLabel: string;
  /** Screen-reader sentence for the live region: «Paso 2 de 4». */
  stepOfLabel: (n: number, total: number) => string;
  variant?: "pills" | "line";
  className?: string;
};

/**
 * Where you are in a short flow (Bloque C): the client wizard. Done steps
 * get a check, the current one is the only one with ``aria-current``, and a
 * polite live region says «paso n de N» when it changes so the position is
 * announced without reading the whole list.
 */
function Stepper({ steps, current, ariaLabel, stepOfLabel, variant = "pills", className }: StepperProps) {
  return (
    <nav aria-label={ariaLabel} className={cn("min-w-0", className)} data-slot="stepper">
      <ol className={cn("flex flex-wrap font-mono text-xs", variant === "pills" ? "gap-2" : "gap-4")}>
        {steps.map((s, i) => {
          const state = i < current ? "done" : i === current ? "current" : "todo";
          return (
            <li
              key={s.key}
              data-state={state}
              aria-current={state === "current" ? "step" : undefined}
              className={cn(
                "flex items-center gap-2",
                variant === "pills" && "rounded-full border px-3 py-1",
                variant === "pills" && state === "current" && "border-foreground text-foreground",
                variant === "pills" && state === "done" && "border-status-positive-border bg-status-positive-bg text-foreground",
                variant === "pills" && state === "todo" && "border-border text-muted-foreground",
                variant === "line" && "border-b-2 pb-1",
                variant === "line" && state === "current" && "border-foreground text-foreground",
                variant === "line" && state === "done" && "border-primary text-foreground",
                variant === "line" && state === "todo" && "border-border text-muted-foreground",
              )}
            >
              <span className="tabular-nums" aria-hidden="true">
                {i + 1}
              </span>
              <span>{s.label}</span>
              {state === "done" ? <Check className="size-3" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {stepOfLabel(current + 1, steps.length)}
      </p>
    </nav>
  );
}

export { Stepper, type StepperProps };
