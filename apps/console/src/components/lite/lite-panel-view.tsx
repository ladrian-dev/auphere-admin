import { ArrowDownRight, ArrowUpRight, Bot, Hand, Wallet } from "lucide-react";

import { Alert, AlertDescription, HighlightMetric, Metric, PageHeader, Section, formatNumber } from "@nexus/ui";

import { ConversationsChart } from "@/components/home/conversations-chart";
import { creditRunway, trendDelta } from "@/components/home/home-model";
import type { Locale, MessageKey } from "@/i18n/messages";
import type { HomeTrend } from "@/lib/backend/home-usage";
import type { LiteHome, LiteMe } from "@/lib/backend/lite";
import { formatMoneyCompact } from "@/lib/money";

import { LiteAttention } from "./lite-attention";
import { LiteSpendCard } from "./lite-spend-card";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

export type LitePanelWho = { name: string; clientName: string; modules: readonly string[] };

/**
 * The Panel of one client (spec 030, US3) — pure, so every state is testable
 * without a request. `home === null` is the whole read failing; `errors`
 * lists the blocks that did not load (partial). Each block is absent when
 * its data is absent: no inbox, no «waiting» card; no allocation, a balance
 * card that says so instead of an invented zero.
 */
export function LitePanelView({
  who,
  home,
  contact,
  t,
  locale,
  now = new Date(),
}: {
  who: LitePanelWho;
  home: LiteHome | null;
  contact: LiteMe["balance_contact"] | null;
  t: T;
  locale: Locale;
  now?: Date;
}) {
  const n = (v: number) => formatNumber(v, locale);
  const first = who.name.split(" ")[0] || who.name;
  const conv = home?.conversations ?? null;
  const delta = conv ? trendDelta(conv.last_7d, conv.prev_7d) : null;
  const trend: HomeTrend | null = conv
    ? { days: conv.daily.map((d) => d.day), series: conv.daily.map((d) => d.count), current: conv.last_7d, previous: conv.prev_7d, by_client: [] }
    : null;
  const balance = home?.balance ?? null;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents, balance.days_left, now) : null;
  const hasUsage = who.modules.includes("usage");

  return (
    <>
      <PageHeader eyebrow={who.clientName} title={t("lite.panel.greeting", { name: first })} size="compact" />
      {home === null ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{t("common.error.backend")}</AlertDescription>
        </Alert>
      ) : null}
      {home && home.errors.length > 0 ? (
        <Alert role="status">
          <AlertDescription>{t("lite.panel.partial")}</AlertDescription>
        </Alert>
      ) : null}

      {home ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {home.spend_month ? (
            <div className="lg:row-span-2">
              <LiteSpendCard spend={home.spend_month} showUsageLink={hasUsage} t={t} locale={locale} />
            </div>
          ) : null}
          <section className={home.spend_month ? "@container lg:col-span-2" : "@container lg:col-span-3"} aria-label={t("lite.panel.kpis")}>
            <div className="grid gap-4 @xl:grid-cols-3">
              {conv && delta ? (
                <HighlightMetric
                  icon={<Bot />}
                  label={t("lite.kpi.conversations")}
                  value={n(conv.last_7d)}
                  delta={
                    delta.kind === "none"
                      ? undefined
                      : {
                          label: (
                            <>
                              {delta.kind === "up" ? <ArrowUpRight aria-hidden="true" /> : delta.kind === "down" ? <ArrowDownRight aria-hidden="true" /> : null}
                              {delta.kind === "same" ? "=" : `${n(delta.pct)} %`}
                            </>
                          ),
                          srLabel: t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) }),
                        }
                  }
                  trend={{ values: conv.daily.map((d) => d.count), ariaLabel: t("hu.home.kpi.conversations.trend") }}
                  hint={delta.kind === "none" ? t("hu.home.kpi.delta.none") : t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) })}
                  href={who.modules.includes("inbox") ? "/inbox" : undefined}
                />
              ) : null}
              {home.waiting ? (
                <Metric
                  icon={<Hand />}
                  label={t("lite.kpi.waiting")}
                  value={n(home.waiting.count)}
                  hint={t("lite.kpi.waiting.hint")}
                  href={
                    home.waiting.first_conversation_id ? `/inbox?c=${encodeURIComponent(home.waiting.first_conversation_id)}` : "/inbox"
                  }
                />
              ) : null}
              {balance ? (
                <Metric
                  icon={<Wallet />}
                  label={t("lite.kpi.balance")}
                  value={balance.assigned && balance.remaining_cents != null ? formatMoneyCompact(balance.remaining_cents, locale) : "—"}
                  progress={
                    runway
                      ? {
                          value: runway.days,
                          max: runway.monthLeft,
                          tone: runway.tone,
                          label: t("lite.kpi.balance.runway.aria"),
                          valueLabel: t("lite.kpi.balance.runway", { days: n(runway.days), left: n(runway.monthLeft) }),
                        }
                      : undefined
                  }
                  hint={
                    !balance.assigned
                      ? t("lite.kpi.balance.unassigned")
                      : (balance.remaining_cents ?? 0) <= 0
                        ? t("lite.kpi.balance.out")
                        : runway
                          ? undefined
                          : t("lite.kpi.balance.noSpend")
                  }
                  className={balance.assigned && (balance.remaining_cents ?? 0) <= 0 ? "ring-status-danger/40" : undefined}
                  href={hasUsage ? "/usage" : undefined}
                />
              ) : null}
            </div>
          </section>
          {trend ? (
            <Section title={t("hu.home.chart.title")} className={home.spend_month ? "lg:col-span-2" : "lg:col-span-3"}>
              <ConversationsChart trend={trend} />
            </Section>
          ) : null}
        </div>
      ) : null}

      {home ? <LiteAttention home={home} contact={contact} modules={who.modules} t={t} n={n} /> : null}
    </>
  );
}
