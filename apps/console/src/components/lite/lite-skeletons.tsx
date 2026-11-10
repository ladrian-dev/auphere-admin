import { Bot, CircleDollarSign, Hand, MessageCircle, Wallet } from "lucide-react";

import { Metric, Skeleton } from "@nexus/ui";

import type { MessageKey } from "@/i18n/messages";

import { LiteReservasSkeleton } from "./lite-reservas";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * Spec 045 (R6.5): the client's Panel and Consumo while they load, with the
 * final dimensions — the same grid, the same cards in the same places, the
 * names that are already known written and only the figures pending. When
 * the data arrives nothing jumps.
 */

/** A card's head as the lite cards draw it: the tinted icon square and its name. */
function CardHead({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary [&_svg]:size-4">
        {icon}
      </span>
      <p className="min-w-0 truncate text-sm font-medium">{title}</p>
    </div>
  );
}

/** The day bars (`DayBars`): the average line, the 160 px of bars and the day labels. */
function ChartBody() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-24 self-end" />
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}

/** `PageHeader`: eyebrow, title and the line under it; `compact` is the Panel's. */
function HeadSkeleton({ compact }: { compact?: boolean }) {
  return (
    <div className={compact ? "flex flex-col gap-1 border-b border-border pb-3" : "flex flex-col gap-2 border-b border-border pb-6"}>
      <Skeleton className="h-4 w-32" />
      <Skeleton className={compact ? "h-7 w-48" : "h-9 w-40"} />
      {compact ? null : <Skeleton className="h-6 w-96 max-w-full" />}
    </div>
  );
}

export function LitePanelSkeleton({ t, modules }: { t: T; modules: readonly string[] }) {
  return (
    <div role="status" aria-label={t("ui.loading")} aria-busy="true" className="flex min-w-0 flex-col gap-6" data-slot="lite-panel-skeleton">
      <HeadSkeleton compact />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:row-span-2">
          <div className="flex h-full flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10">
            <CardHead icon={<CircleDollarSign />} title={t("lite.spend.title")} />
            <Skeleton className="h-10 w-40" />
          </div>
        </div>
        <div className="@container lg:col-span-2">
          <div className="grid gap-4 @xl:grid-cols-3">
            <Metric loading icon={<Bot />} label={t("lite.kpi.conversations")} value="" hint=" " />
            {modules.includes("inbox") ? <Metric loading icon={<Hand />} label={t("lite.kpi.waiting")} value="" hint=" " /> : null}
            <Metric loading icon={<Wallet />} label={t("lite.kpi.balance")} value="" hint=" " />
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-(--space-stack) rounded-md bg-card p-4 ring-1 ring-foreground/10 lg:col-span-2">
          <p className="text-base font-medium">{t("hu.home.chart.title")}</p>
          <ChartBody />
        </div>
      </div>
      {modules.includes("reservas") ? <LiteReservasSkeleton t={t} /> : null}
      <Skeleton className="h-12 w-full" />
    </div>
  );
}

export function LiteUsageSkeleton({ t }: { t: T }) {
  return (
    <div role="status" aria-label={t("ui.loading")} aria-busy="true" className="flex min-w-0 flex-col gap-6" data-slot="lite-usage-skeleton">
      <HeadSkeleton />
      <div className="grid gap-4 md:grid-cols-2" data-slot="lite-usage-cards">
        <div className="flex min-w-0 flex-col gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10 md:row-span-2">
          <CardHead icon={<Wallet />} title={t("lite.kpi.balance")} />
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-6 w-56 max-w-full" />
          <div className="mt-auto flex flex-col gap-1">
            <Skeleton className="h-4 w-40 self-end" />
            <Skeleton className="h-1 w-full rounded-full" />
          </div>
        </div>
        <Metric loading icon={<CircleDollarSign />} label={t("lite.spend.title")} value="" hint=" " />
        <Metric loading icon={<MessageCircle />} label={t("lite.usage.conversations")} value="" hint=" " />
      </div>
      <div className="flex min-w-0 flex-col gap-(--space-stack) rounded-md bg-card p-4 ring-1 ring-foreground/10">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="text-base font-medium">{t("hu.usage.spend.title")}</p>
          <Skeleton className="h-8 w-48" />
        </div>
        <ChartBody />
      </div>
      <div className="flex flex-col gap-1 rounded-md bg-card p-4 ring-1 ring-foreground/10">
        <p className="text-sm font-medium">{t("hu.usage.detail.title")}</p>
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
    </div>
  );
}
