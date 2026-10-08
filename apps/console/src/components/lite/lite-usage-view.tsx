import { BarChart3, CircleDollarSign, MessageCircle, Wallet } from "lucide-react";

import { Alert, AlertDescription, EmptyState, Metric, PageHeader, Section, formatNumber } from "@nexus/ui";

import { MeterList } from "@/app/(console)/usage/meter-list";
import { SpendChart } from "@/app/(console)/usage/spend-chart";
import { SpendControls } from "@/app/(console)/usage/spend-controls";
import { creditRunway } from "@/components/home/home-model";
import type { Locale, MessageKey } from "@/i18n/messages";
import type { LiteSpend, LiteUsageDetail, LiteUsageSummary } from "@/lib/backend/lite";
import { meterLabel } from "@/lib/meter-label";
import { formatMoney } from "@/lib/money";
import { meterGroups } from "@/lib/usage-projection";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * The Consumo of one client (spec 030, US4) — read-only, so there is no
 * «Comprar saldo», no tope to change and no alerts to set (C2: Auphere bills
 * the partner). The same money the partner sees for this client; never
 * Auphere's cost. Pure: every state is testable.
 */
export function LiteUsageView({
  clientName,
  summary,
  spend,
  detail,
  days,
  agent = "",
  agents = [],
  t,
  locale,
  now = new Date(),
}: {
  clientName: string;
  summary: LiteUsageSummary | null;
  spend: LiteSpend | null;
  detail: LiteUsageDetail | null;
  days: number;
  /** Spec 030: the spend chart of one agent; `agents` is empty with one. */
  agent?: string;
  agents?: Array<{ id: string; name: string }>;
  t: T;
  locale: Locale;
  now?: Date;
}) {
  const n = (v: number) => formatNumber(v, locale);
  const money = (cents: number) => formatMoney(cents, locale);
  const balance = summary?.balance ?? null;
  const month = summary?.month ?? null;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents, balance.days_left, now) : null;
  const byAgent = summary?.by_agent && summary.by_agent.length > 1 ? summary.by_agent : null;

  return (
    <>
      <PageHeader eyebrow={clientName} title={t("nav.usage")} description={byAgent ? t("lite.usage.intro.agents") : t("lite.usage.intro")} />
      {summary === null ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{t("common.error.backend")}</AlertDescription>
        </Alert>
      ) : summary.errors.length > 0 ? (
        <Alert role="status">
          <AlertDescription>{t("lite.usage.partial")}</AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3" aria-label={t("lite.usage.cards")}>
        <Metric
          icon={<Wallet />}
          label={t("lite.kpi.balance")}
          value={balance?.assigned && balance.remaining_cents != null ? money(balance.remaining_cents) : "—"}
          progress={
            runway
              ? {
                  value: runway.days,
                  max: runway.monthLeft,
                  tone: runway.tone,
                  label: t("lite.kpi.balance.runway.aria"),
                  valueLabel: t("lite.usage.balance.runway", { days: n(runway.days) }),
                }
              : undefined
          }
          hint={
            balance === null
              ? t("lite.usage.unreadable")
              : !balance.assigned
                ? t("lite.kpi.balance.unassigned")
                : (balance.remaining_cents ?? 0) <= 0
                  ? t("lite.kpi.balance.out")
                  : runway
                    ? undefined
                    : t("lite.kpi.balance.noSpend")
          }
        />
        <Metric
          icon={<CircleDollarSign />}
          label={t("lite.spend.title")}
          value={month ? money(month.spent_cents) : "—"}
          hint={
            month === null
              ? t("lite.usage.unreadable")
              : month.projection_cents != null && month.spent_cents > 0
                ? t("lite.usage.month.projection", { amount: money(month.projection_cents) })
                : t("lite.usage.month.none")
          }
        />
        <Metric
          icon={<MessageCircle />}
          label={t("lite.usage.conversations")}
          value={month?.conversations != null ? n(month.conversations) : "—"}
          hint={
            month?.avg_per_conversation_cents != null
              ? t("lite.usage.conversations.avg", { amount: money(month.avg_per_conversation_cents) })
              : month === null
                ? t("lite.usage.unreadable")
                : undefined
          }
        />
      </section>

      {byAgent ? (
        <Section padded={false} title={t("lite.usage.byAgent.title")}>
          <table className="w-full text-sm">
            <caption className="sr-only">{t("lite.usage.byAgent.title")}</caption>
            <thead>
              <tr className="border-b text-left">
                <th className="h-10 px-4 font-medium">{t("lite.usage.byAgent.agent")}</th>
                <th className="h-10 px-4 text-right font-medium">{t("lite.usage.conversations")}</th>
                <th className="h-10 px-4 text-right font-medium">{t("lite.usage.byAgent.spent")}</th>
                <th className="h-10 px-4 font-medium">{t("lite.usage.byAgent.share")}</th>
              </tr>
            </thead>
            <tbody>
              {byAgent.map((a) => (
                <tr key={a.agent_id} className="border-b last:border-0">
                  <td className="max-w-64 truncate px-4 py-2 font-medium" title={a.name}>
                    {a.name}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{n(a.conversations)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{money(a.spent_cents)}</td>
                  <td className="px-4 py-2">
                    <span className="flex items-center gap-3">
                      <span className="h-1 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                        {/* Inline width on purpose: it is the datum (the agent's share), not a style. */}
                        <span className="block h-full rounded-full bg-primary" style={{ width: `${a.share_pct}%` }} />
                      </span>
                      <span className="w-10 text-right text-xs text-muted-foreground tabular-nums">{n(a.share_pct)} %</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      <Section id="gasto" title={t("hu.usage.spend.title")} actions={<SpendControls days={days} client="" clients={[]} showClient={false} agent={agent} agents={agents} />}>
        {spend ? (
          <SpendChart spend={{ ...spend, by_client: [], month_cents: spend.month_cents, projected_cents: spend.projected_cents, month_by_client: [] }} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">{t("hu.usage.spend.unreadable")}</p>
        )}
      </Section>

      <details className="group rounded-md bg-card ring-1 ring-foreground/10">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 p-4 text-sm font-medium">
          <span>
            {t("hu.usage.detail.title")}
            <span className="block text-xs font-normal text-muted-foreground">{t("lite.usage.detail.hint")}</span>
          </span>
          <span aria-hidden="true" className="text-muted-foreground transition-transform group-open:rotate-90">
            ›
          </span>
        </summary>
        <div className="flex flex-col gap-4 border-t border-border p-4">
          <div className="flex justify-end">
            <a
              href={`/api/lite/usage/export?days=${days}&lang=${locale}`}
              className="inline-flex h-8 items-center gap-2 rounded-sm px-3 text-sm font-medium ring-1 ring-border hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              <BarChart3 className="size-4" aria-hidden="true" />
              {t("usage.export")}
            </a>
          </div>
          {detail === null ? (
            <p className="text-sm text-muted-foreground">{t("lite.usage.unreadable")}</p>
          ) : detail.buckets.length === 0 ? (
            <EmptyState title={t("usage.empty")} description={t("usage.period", { days })} readonly />
          ) : (
            <>
              <MeterList groups={meterGroups([], detail.totals_by_meter)} t={t} locale={locale} />
              <div className="max-h-112 min-w-0 overflow-auto rounded-md ring-1 ring-foreground/10">
                <table className="w-full text-sm">
                  <caption className="sr-only">{t("hu.usage.detail.title")}</caption>
                  <thead>
                    <tr className="sticky top-0 border-b bg-card text-left">
                      <th className="h-10 px-2 font-medium">{t("usage.meter")}</th>
                      <th className="h-10 px-2 text-right font-medium">{t("usage.quantity")}</th>
                      <th className="h-10 px-2 text-right font-medium">{t("usage.billable")}</th>
                      <th className="h-10 px-2 text-right font-medium">{t("usage.records")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.buckets.map((b, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="p-2" title={b.meter}>
                          {meterLabel(b.meter, t)}
                        </td>
                        <td className="p-2 text-right tabular-nums">{n(b.quantity)}</td>
                        <td className="p-2 text-right tabular-nums">{n(b.billable_qty)}</td>
                        <td className="p-2 text-right tabular-nums">{n(b.records)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </details>
    </>
  );
}
