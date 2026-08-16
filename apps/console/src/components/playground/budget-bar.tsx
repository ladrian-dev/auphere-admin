"use client";

import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle, formatDate, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";
import type { PlaygroundBudget } from "@/lib/backend/playground";

/**
 * Monthly cap of the playground, in tokens (C9). Three looks: normal,
 * near the cap (≥ 80 %), reached (input disabled elsewhere).
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
    return <div className="h-2 w-full animate-pulse rounded-full bg-muted" aria-hidden="true" />;
  }
  const pct = Math.min(100, Math.max(0, budget.percent));
  const near = !budget.exhausted && pct >= 80;
  // Native <progress>: semantics + a11y for free, and no inline style for
  // the dynamic width (the value IS the width). Tone via pseudo-elements.
  const tone = budget.exhausted
    ? "[&::-webkit-progress-value]:bg-status-danger [&::-moz-progress-bar]:bg-status-danger"
    : near
      ? "[&::-webkit-progress-value]:bg-status-warning [&::-moz-progress-bar]:bg-status-warning"
      : "[&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary";
  const label = t("playground.budget.usage", {
    used: formatNumber(budget.used, locale),
    cap: formatNumber(budget.cap, locale),
    percent: formatNumber(pct, locale, { maximumFractionDigits: 0 }),
  });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{t("playground.budget")}</span>
        <span className="truncate font-mono text-xs tabular-nums text-muted-foreground" title={label}>
          {label}
        </span>
      </div>
      <progress
        value={Math.round(pct)}
        max={100}
        aria-label={t("playground.budget")}
        aria-valuetext={label}
        className={[
          "h-2 w-full appearance-none overflow-hidden rounded-full bg-muted",
          "[&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:rounded-full [&::-moz-progress-bar]:rounded-full",
          tone,
        ].join(" ")}
      />
      <p className="text-xs text-muted-foreground">
        {t("playground.budget.resets", { date: formatDate(budget.resets_at, locale) })}
      </p>
      {near ? (
        <p className="text-xs text-status-warning" role="status">
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
