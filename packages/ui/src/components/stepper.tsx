import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/utils";

type StepState = "done" | "current" | "todo";

type StepperProps = {
  /** ``state`` overrides the position rule for that step: steps are not
   *  always sequential (a client can have credit before a channel). */
  steps: { key: string; label: ReactNode; state?: StepState }[];
  /** Index of the current step (used for every step without ``state``). */
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
      <ol className={cn("flex flex-wrap text-sm", variant === "pills" ? "gap-2" : "gap-x-6 gap-y-2")}>
        {steps.map((s, i) => {
          const state: StepState = s.state ?? (i < current ? "done" : i === current ? "current" : "todo");
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
                variant === "line" && state === "current" && "font-medium text-foreground",
                variant === "line" && state === "done" && "text-foreground",
                variant === "line" && state === "todo" && "text-muted-foreground",
              )}
            >
              {variant === "line" ? (
                <span
                  aria-hidden="true"
                  className={cn(
                    "grid size-6 shrink-0 place-items-center rounded-full border text-xs tabular-nums",
                    state === "done" && "border-primary bg-primary text-primary-foreground",
                    state === "current" && "border-foreground text-foreground",
                    state === "todo" && "border-border text-muted-foreground",
                  )}
                >
                  {state === "done" ? <Check className="size-3" /> : i + 1}
                </span>
              ) : (
                <span className="tabular-nums" aria-hidden="true">
                  {i + 1}
                </span>
              )}
              <span>{s.label}</span>
              {variant === "pills" && state === "done" ? <Check className="size-3" aria-hidden="true" /> : null}
              {variant === "line" && i < steps.length - 1 ? <span aria-hidden="true" className="ml-2 hidden h-px w-8 bg-foreground/20 sm:block" /> : null}
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

export { Stepper, type StepperProps, type StepState };
