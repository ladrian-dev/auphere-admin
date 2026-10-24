"use client";

import { Check } from "lucide-react";
import { usePathname } from "next/navigation";

import { cn } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { WIZARD_STEPS, stepOf } from "./steps";

/**
 * Spec 046: the rail of «Añadir canal» — numbered steps, the done ones
 * checked. Wide screens get it on the left with one line per step; narrow
 * ones a single row on top, so the step itself keeps the width.
 */
export function WizardSteps({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const current = stepOf(usePathname() ?? "");
  return (
    <ol className={compact ? "flex flex-wrap items-center gap-x-5 gap-y-2" : "flex flex-col gap-6"} aria-label={t("chw.steps")}>
      {WIZARD_STEPS.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s.title} className={compact ? "flex items-center gap-2" : "flex gap-3"} aria-current={active ? "step" : undefined}>
            <span
              className={cn(
                "grid shrink-0 place-items-center rounded-full font-medium tabular-nums",
                compact ? "size-6 text-xs" : "size-8 text-sm",
                done ? "bg-primary text-primary-foreground" : active ? "bg-primary/15 text-primary-text" : "bg-muted text-muted-foreground",
              )}
            >
              {done ? <Check className={compact ? "size-3" : "size-4"} aria-hidden="true" /> : i + 1}
            </span>
            {compact ? (
              <span className={cn("text-sm", active ? "font-medium text-primary-text" : "text-muted-foreground")}>{t(s.title)}</span>
            ) : (
              <span className="flex flex-col gap-1">
                <span className={cn("text-sm font-medium", active ? "text-primary-text" : done ? "" : "text-muted-foreground")}>{t(s.title)}</span>
                <span className="text-sm text-pretty text-muted-foreground">{t(s.body)}</span>
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
