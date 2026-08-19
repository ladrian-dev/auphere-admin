"use client";

import { formatCompact, formatDate, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import type { BudgetMeter, ContextMeter, CostMeter } from "./state";

/**
 * The three gauges of the drawer footer (§12): context window, turn cost
 * in tokens, monthly cap.
 *
 * **A missing gauge is a valid state, and the right one.** If the model is
 * not in `model_profiles` the API never emits `context.updated` (§2.6), and
 * a bar sitting at 0 % would be worse than no bar at all — people believe
 * a bar. Same for cost before the first turn.
 *
 * `percent` always comes from the backend (`input_tokens / max_context`),
 * never estimated from character counts here.
 *
 * Tokens, never dollars: the partner sees what it spent, priced by us
 * elsewhere (decision C9).
 */
export function Meters({
  cost,
  context,
  budget,
}: {
  cost: CostMeter | null;
  context: ContextMeter | null;
  budget: BudgetMeter | null;
}) {
  const t = useT();
  const locale = useLocale();

  if (!cost && !context && !budget) return null;

  return (
    <dl className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-xs">
      {context ? (
        <div className="flex min-w-0 items-center gap-2">
          <dt className="shrink-0 text-muted-foreground">{t("companion.meter.context")}</dt>
          <dd className="flex min-w-0 items-center gap-2">
            <Bar
              percent={context.percent}
              label={t("companion.meter.context.detail", {
                used: formatNumber(context.input, locale),
                max: formatNumber(context.max, locale),
                percent: Math.round(context.percent),
              })}
            />
            <span className="shrink-0 font-mono tabular-nums text-muted-foreground">{Math.round(context.percent)}%</span>
          </dd>
        </div>
      ) : null}

      {cost ? (
        <div className="flex min-w-0 items-center gap-2">
          <dt className="shrink-0 text-muted-foreground">{t("companion.meter.turn")}</dt>
          <dd
            className="shrink-0 font-mono tabular-nums text-muted-foreground"
            title={t("companion.meter.turn.detail", {
              input: formatNumber(cost.input, locale),
              output: formatNumber(cost.output, locale),
            })}
          >
            {formatCompact(cost.input + cost.output, locale)}
            <span className="sr-only">
              {" "}
              {t("companion.meter.turn.detail", {
                input: formatNumber(cost.input, locale),
                output: formatNumber(cost.output, locale),
              })}
            </span>
          </dd>
        </div>
      ) : null}

      {budget ? (
        <div className="flex min-w-0 items-center gap-2">
          <dt className="shrink-0 text-muted-foreground">{t("companion.meter.month")}</dt>
          <dd className="flex min-w-0 items-center gap-2">
            <Bar
              percent={budget.percent}
              tone={budget.exhausted ? "danger" : budget.percent >= 80 ? "warning" : "default"}
              label={t("companion.meter.month.detail", {
                used: formatNumber(budget.used, locale),
                cap: formatNumber(budget.cap, locale),
                percent: Math.round(budget.percent),
              })}
            />
            <span
              className={`shrink-0 font-mono tabular-nums ${budget.exhausted ? "text-status-danger" : "text-muted-foreground"}`}
            >
              {Math.round(budget.percent)}%
            </span>
            {budget.resetsAt ? (
              <span className="sr-only">
                {t("companion.meter.month.resets", { date: formatDate(budget.resetsAt, locale) })}
              </span>
            ) : null}
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

/**
 * Native `<progress>`, same as the playground's budget bar: semantics and
 * accessibility for free, and — the reason it matters here — **no inline
 * style for the dynamic width**, because the value IS the width. Tone
 * comes from pseudo-element utilities, so every colour stays a token.
 */
function Bar({
  percent,
  label,
  tone = "default",
}: {
  percent: number;
  label: string;
  tone?: "default" | "warning" | "danger";
}) {
  const clamped = Math.min(100, Math.max(0, percent));
  const fill =
    tone === "danger"
      ? "[&::-webkit-progress-value]:bg-status-danger [&::-moz-progress-bar]:bg-status-danger"
      : tone === "warning"
        ? "[&::-webkit-progress-value]:bg-status-warning [&::-moz-progress-bar]:bg-status-warning"
        : "[&::-webkit-progress-value]:bg-primary [&::-moz-progress-bar]:bg-primary";
  return (
    <progress
      value={Math.round(clamped)}
      max={100}
      aria-label={label}
      aria-valuetext={label}
      className={[
        "h-2 w-16 shrink-0 appearance-none overflow-hidden rounded-full bg-muted",
        "[&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:rounded-full [&::-moz-progress-bar]:rounded-full",
        fill,
      ].join(" ")}
    />
  );
}
