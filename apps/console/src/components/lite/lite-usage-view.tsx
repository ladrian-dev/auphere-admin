import { BarChart3, CircleDollarSign, MessageCircle } from "lucide-react";

import { Alert, AlertDescription, EmptyState, Metric, PageHeader, Section, formatNumber } from "@nexus/ui";

import { SpendChart } from "@/app/(console)/usage/spend-chart";
import { SpendControls } from "@/app/(console)/usage/spend-controls";
import type { Locale, MessageKey } from "@/i18n/messages";
import type { LiteSpend, LiteUsageDetail, LiteUsageSummary } from "@/lib/backend/lite";
import { formatMoney } from "@/lib/money";

import { LiteBalanceCard } from "./lite-balance-card";
import { detailFamilies } from "./lite-model";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/**
 * The Consumo of one client (spec 030, US4) — read-only, so there is no
 * «Comprar saldo», no tope to change and no alerts to set (C2: Auphere bills
 * the partner). The same money the partner sees for this client; never
 * Auphere's cost. Pure: every state is testable.
 *
 * Spec 045 (R6.3): the balance goes first and big, with until when it lasts;
 * the technical detail is one WhatsApp row in three families (messages,
 * model usage, media) and the period's spend. Only WhatsApp by Meta is in
 * use, so there is no row or tab of another channel.
 */
export function LiteUsageView({
  clientName,
  summary,
  spend,
  detail,
  periodSpend,
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
  /** The client's whole spend over `days` when the chart is narrowed to one
   *  agent; without it, `spend` is already the whole one. */
  periodSpend?: LiteSpend | null;
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
  const byAgent = summary?.by_agent && summary.by_agent.length > 1 ? summary.by_agent : null;
  const whole = periodSpend !== undefined ? periodSpend : agent ? null : spend;
  const periodCents = whole ? whole.series_cents.reduce((sum, c) => sum + c, 0) : null;

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

      {/* The balance first and big (spec 045): it answers «until when» before
          anything else. Spend and conversations stack beside it. */}
      <section className="grid gap-4 md:grid-cols-2" aria-label={t("lite.usage.cards")}>
        <LiteBalanceCard balance={balance} t={t} locale={locale} now={now} className="md:row-span-2" />
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
          <span aria-hidden="true" className="text-muted-foreground transition-transform group-open:rotate-90 motion-reduce:transition-none">
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
            <DetailTable totals={detail.totals_by_meter} periodCents={periodCents} days={days} t={t} locale={locale} />
          )}
        </div>
      </details>
    </>
  );
}

/**
 * The technical detail (spec 045, R6.3): one row, WhatsApp —the only channel
 * in use—, the meters added up in their families, each in its own unit, and
 * the money the period cost. The families do not add up to that money: the
 * API measures quantities per meter, not money per meter, so the money is
 * the period's spend and says so in its header.
 */
function DetailTable({
  totals,
  periodCents,
  days,
  t,
  locale,
}: {
  totals: Record<string, number>;
  periodCents: number | null;
  days: number;
  t: T;
  locale: Locale;
}) {
  const n = (v: number) => formatNumber(v, locale);
  const families = detailFamilies(totals);
  const unit = "block text-xs font-normal text-muted-foreground";
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-xs text-muted-foreground">{t("usage.period", { days })}</p>
      {/* Its own horizontal scroll: five columns do not fit a 360 px phone.
          Focusable, so a keyboard can scroll it too (WCAG 2.1.1). */}
      <div
        role="region"
        aria-label={t("hu.usage.detail.title")}
        tabIndex={0}
        className="min-w-0 overflow-x-auto rounded-md ring-1 ring-foreground/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <table className="w-full min-w-xl text-sm">
          <caption className="sr-only">{t("hu.usage.detail.title")}</caption>
          <thead>
            <tr className="border-b text-left align-bottom">
              <th scope="col" className="h-10 px-4 py-2 font-medium">
                {t("lite.usage.detail.channel")}
              </th>
              <th scope="col" className="h-10 px-4 py-2 text-right font-medium">
                {t("hu.usage.meters.messages")}
              </th>
              <th scope="col" className="h-10 px-4 py-2 text-right font-medium">
                {t("hu.usage.meters.model")}
                <span className={unit}>{t("lite.usage.detail.unit.model")}</span>
              </th>
              <th scope="col" className="h-10 px-4 py-2 text-right font-medium">
                {t("hu.usage.meters.media")}
                <span className={unit}>{t("lite.usage.detail.unit.media")}</span>
              </th>
              {families.other != null ? (
                <th scope="col" className="h-10 px-4 py-2 text-right font-medium">
                  {t("hu.usage.meters.other")}
                  <span className={unit}>{t("lite.usage.detail.unit.other")}</span>
                </th>
              ) : null}
              <th scope="col" className="h-10 px-4 py-2 text-right font-medium">
                {t("lite.usage.detail.spend")}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row" className="px-4 py-3 text-left font-medium">
                {t("inbox.channel.whatsapp")}
              </th>
              <td className="px-4 py-3 text-right tabular-nums">{n(families.messages)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{n(families.model)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{n(families.media)}</td>
              {families.other != null ? <td className="px-4 py-3 text-right tabular-nums">{n(families.other)}</td> : null}
              <td className="px-4 py-3 text-right font-medium tabular-nums">{periodCents == null ? "—" : formatMoney(periodCents, locale)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
