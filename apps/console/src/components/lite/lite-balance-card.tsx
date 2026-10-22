import { Wallet } from "lucide-react";

import { Meter, cn, formatNumber } from "@nexus/ui";

import type { Locale, MessageKey } from "@/i18n/messages";
import type { LiteBalance } from "@/lib/backend/lite";

import { balanceRunway, runsOutDate } from "./lite-model";
import { MoneyFigure } from "./lite-spend-card";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * The balance at the head of Consumo (spec 045, R4, R6.3): what is left, big,
 * and the question it answers first — until when it lasts. Read-only (C2):
 * no buy, no alerts. Each case says what it is and nothing it cannot know:
 * no allocation is not a zero, no spend is no date, a used-up balance is
 * «the agent stopped», never «it lasts until today».
 */
export function LiteBalanceCard({
  balance,
  t,
  locale,
  now,
  className,
}: {
  /** `null`: the balance could not be read. */
  balance: LiteBalance | null;
  t: T;
  locale: Locale;
  now: Date;
  className?: string;
}) {
  const n = (v: number) => formatNumber(v, locale);
  const runway = balanceRunway(balance);
  const remaining = balance?.assigned ? balance.remaining_cents : null;
  const usedUp = remaining != null && remaining <= 0;
  const until = !usedUp && balance?.days_left != null ? runsOutDate(balance.runs_out_on, locale, now) : null;
  const hint =
    balance === null
      ? t("lite.usage.unreadable")
      : !balance.assigned
        ? t("lite.kpi.balance.unassigned")
        : usedUp
          ? t("lite.kpi.balance.out")
          : balance.days_left == null
            ? t("lite.kpi.balance.noSpend")
            : null;

  return (
    <section
      aria-labelledby="lite-balance-h"
      data-slot="lite-balance"
      className={cn("flex min-w-0 flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10", usedUp && "ring-status-danger/40", className)}
    >
      <div className="flex min-w-0 items-center gap-2">
        <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
          <Wallet className="size-4" />
        </span>
        <h2 id="lite-balance-h" className="min-w-0 truncate text-sm font-medium">
          {t("lite.kpi.balance")}
        </h2>
      </div>
      {remaining != null ? <MoneyFigure cents={remaining} locale={locale} /> : <p className="text-4xl font-semibold tracking-tight text-muted-foreground">—</p>}
      {until ? <p className="text-base font-medium text-pretty">{t("lite.usage.balance.until", { date: until })}</p> : null}
      {runway ? (
        <Meter
          className="mt-auto"
          size="sm"
          label={t("lite.kpi.balance.runway.aria")}
          labelHidden
          value={runway.days}
          max={runway.monthLeft}
          valueLabel={t("lite.kpi.balance.runway", { days: n(runway.days), left: n(runway.monthLeft) })}
          tone={runway.tone}
        />
      ) : null}
      {hint ? <p className="text-sm text-pretty text-muted-foreground">{hint}</p> : null}
    </section>
  );
}
