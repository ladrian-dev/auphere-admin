"use client";

import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle, Meter, formatDate, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { PlaygroundBudget } from "@/lib/backend/playground";

/**
 * Monthly cap of the playground, in tokens (C9). Three looks: normal,
 * near the cap (≥ 80 %), reached (input disabled elsewhere). The bar is
 * the DS Meter (Bloque C); this file keeps the copy and the two notices.
 */
export function BudgetBar({ budget, error, onRetry }: { budget: PlaygroundBudget | null; error?: boolean; onRetry?: () => void }) {
  const t = useT();
  const locale = useLocale();
  if (error && !budget) {
    return (
      <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground" role="status">
        <span>{t("playground.budget.error")}</span>
        {onRetry ? (
          <button type="button" className="underline underline-offset-4 hover:text-foreground" onClick={onRetry}>
            {t("playground.run.retry")}
          </button>
        ) : null}
      </div>
    );
  }
  if (!budget) {
    return <Meter label={t("playground.budget")} labelHidden value={0} max={1} loading />;
  }
  const pct = Math.min(100, Math.max(0, budget.percent));
  const near = !budget.exhausted && pct >= 80;
  const label = t("playground.budget.usage", {
    used: formatNumber(budget.used, locale),
    cap: formatNumber(budget.cap, locale),
    percent: formatNumber(pct, locale, { maximumFractionDigits: 0 }),
  });
  return (
    <div className="flex flex-col gap-2">
      <Meter
        label={t("playground.budget")}
        value={budget.used}
        max={budget.cap}
        tone={budget.exhausted ? "danger" : "auto"}
        valueLabel={label}
        hint={t("playground.budget.resets", { date: formatDate(budget.resets_at, locale) })}
      />
      {near ? (
        <p className="text-xs text-warning" role="status">
          {t("playground.budget.near", { remaining: formatNumber(budget.remaining, locale) })}
        </p>
      ) : null}
      {budget.exhausted ? (
        <Alert variant="destructive" role="alert">
          <AlertTriangle aria-hidden="true" />
          <AlertTitle>{t("playground.budget.reached")}</AlertTitle>
          <AlertDescription>
            {t("playground.budget.reached.body", {
              cap: formatNumber(budget.cap, locale),
              date: formatDate(budget.resets_at, locale),
            })}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
