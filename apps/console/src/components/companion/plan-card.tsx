"use client";

import { ListChecks, RotateCcw, ShieldAlert } from "lucide-react";

import { Badge, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import type { PlanStep, Risk } from "./types";

/**
 * The plan card (§2.1 of the contract).
 *
 * **A plan commits to nothing.** It may never reach a `hitl.requested` —
 * the user changes their mind, or the investigation invalidates it — so
 * this card says out loud that nothing has happened yet. Presenting a plan
 * as if it were already in motion is how a tool loses trust the first time
 * someone reads it wrong.
 *
 * `steps[].title` is written by the model and painted verbatim: it is the
 * one string of the plan that does not come from the tool catalogue, and
 * §2.1 says not to translate it.
 *
 * `risk` maps to a token, never to a hex.
 */
const RISK_TONE: Record<Risk, string> = {
  low: "text-status-positive",
  medium: "text-status-warning",
  high: "text-status-danger",
};

export function PlanCard({
  steps,
  risk,
  reversible,
  estimatedTokens,
}: {
  steps: PlanStep[];
  risk: Risk;
  reversible: boolean;
  estimatedTokens: number;
}) {
  const t = useT();
  const locale = useLocale();

  return (
    <section aria-label={t("companion.plan.title")} className="min-w-0 rounded-sm border border-border bg-card p-3">
      <div className="flex min-w-0 items-center gap-2">
        <ListChecks aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <h3 className="min-w-0 flex-1 truncate text-sm font-medium">{t("companion.plan.title")}</h3>
        <Badge variant="outline">
          {steps.length === 1 ? t("companion.plan.step") : t("companion.plan.steps", { n: steps.length })}
        </Badge>
      </div>

      <ol className="mt-2 min-w-0 space-y-2">
        {steps.map((s) => (
          <li key={s.index} className="flex min-w-0 gap-2 text-xs">
            <span className="mt-px shrink-0 font-mono tabular-nums text-muted-foreground">{s.index}.</span>
            <span className="min-w-0 flex-1">
              {/* Written by the model — painted as-is, never translated. */}
              <span className="text-pretty break-words text-foreground">{s.title}</span>
              {s.client_ref ? (
                <span className="ml-1 font-mono text-muted-foreground">
                  · {t("companion.plan.forClient", { ref: s.client_ref })}
                </span>
              ) : null}
            </span>
            {!s.reversible ? (
              <ShieldAlert aria-label={t("companion.plan.irreversible")} className="mt-px size-3 shrink-0 text-status-warning" />
            ) : null}
          </li>
        ))}
      </ol>

      <dl className="mt-3 flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-2 text-xs">
        <div className="flex min-w-0 items-center gap-1">
          <dt className="text-muted-foreground">{t("companion.plan.risk")}</dt>
          <dd className={`font-medium ${RISK_TONE[risk]}`}>{t(`companion.plan.risk.${risk}` as const)}</dd>
        </div>
        <div className="flex min-w-0 items-center gap-1">
          <RotateCcw aria-hidden="true" className="size-3 shrink-0 text-muted-foreground" />
          <dt className="sr-only">{t("companion.plan.reversible")}</dt>
          <dd className={reversible ? "text-muted-foreground" : "font-medium text-status-warning"}>
            {reversible ? t("companion.plan.reversible") : t("companion.plan.irreversible")}
          </dd>
        </div>
        {estimatedTokens > 0 ? (
          <div className="flex min-w-0 items-center gap-1">
            <dt className="sr-only">tokens</dt>
            <dd className="font-mono tabular-nums text-muted-foreground">
              {t("companion.plan.tokens", { n: formatNumber(estimatedTokens, locale) })}
            </dd>
          </div>
        ) : null}
      </dl>

      <p className="mt-2 text-xs text-pretty text-muted-foreground">{t("companion.plan.note")}</p>
    </section>
  );
}
