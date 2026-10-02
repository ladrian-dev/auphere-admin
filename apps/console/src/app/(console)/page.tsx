import { ArrowDownRight, ArrowUpRight, Bot, MessageSquare, Users, Wallet } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { Alert, AlertDescription, Button, CardSkeleton, EmptyState, HighlightMetric, Metric, PageHeader, Section, formatCompact, formatNumber } from "@nexus/ui";

import { ActivityFeed } from "@/components/home/activity-feed";
import { AttentionBlock } from "@/components/home/attention-block";
import { ConversationsChart } from "@/components/home/conversations-chart";
import { creditRunway, roundDays, trendDelta } from "@/components/home/home-model";
import { OnboardingCard } from "@/components/home/onboarding-card";
import { PortfolioTable } from "@/components/home/portfolio-table";
import { ReviewBlock } from "@/components/home/review-block";
import { SpendCard } from "@/components/home/spend-card";
import { WorkstationSetup } from "@/components/workstation/workstation-setup";
import { getT } from "@/i18n/server";
import type { AuditEntry } from "@/lib/backend";
import { backendFor } from "@/lib/backend";
import type { Home } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";


/**
 * Home (spec 026): what fails, what waits for a person, how the week goes,
 * how long the credit lasts and how each client is doing — from ONE call
 * (`GET /console/home`) plus the last audit entries. Each block is gated by
 * permission on the API and is simply absent when it is `null` or failed.
 */
export default async function HomePage() {
  const principal = await requirePrincipal();
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const readAudit = can(principal.role, "audit:read");
  const [home, activity] = await Promise.all([
    api.home().catch((): Home | null => null),
    readAudit ? api.auditV2({ limit: 6, lang: locale }).then((p) => p.items).catch((): AuditEntry[] | null => null) : Promise.resolve(null),
  ]);
  const readClients = can(principal.role, "clients:read");
  const writeClients = can(principal.role, "clients:write");
  const n = (v: number) => formatNumber(v, locale);

  const trend = home?.conversations_trend ?? null;
  const delta = trend ? trendDelta(trend.current, trend.previous) : null;
  const credit = home?.credit ?? null;
  const spend = home?.spend ?? null;
  const runway = credit ? creditRunway(credit.available, credit.days_left, new Date()) : null;
  const runwayProgress = runway
    ? {
        value: runway.days,
        max: runway.monthLeft,
        tone: runway.tone,
        label: t("hu.home.kpi.credit.runway.aria"),
        valueLabel: t("hu.home.kpi.credit.runway", { days: n(runway.days), left: n(runway.monthLeft) }),
      }
    : null;
  const hasPortfolio = Boolean(home?.portfolio && home.portfolio.length > 0);
  const noClients = readClients && home?.clients?.total === 0;

  return (
    <>
      <PageHeader
        eyebrow={principal.partnerName}
        title={t("home.welcome", { name: principal.name })}
        size="compact"
        actions={
          writeClients ? (
            <Button nativeButton={false} render={<Link href="/clients/new" />}>
              {t("hu.home.newClient")}
            </Button>
          ) : undefined
        }
      />
      {home === null ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{t("common.error.backend")}</AlertDescription>
        </Alert>
      ) : null}
      {home && home.errors.length > 0 ? (
        <Alert role="status">
          <AlertDescription>{t("hu.home.partial", { blocks: home.errors.join(", ") })}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        {spend ? (
          <div className="lg:row-span-2">
            <SpendCard spend={spend} dailyCredits={credit?.daily_average ?? null} t={t} locale={locale} />
          </div>
        ) : null}
        <section className={spend ? "grid gap-4 sm:grid-cols-2 lg:col-span-2" : "grid gap-4 sm:grid-cols-2 lg:col-span-3"} aria-label={t("home.title")}>
          {trend && delta ? (
            <HighlightMetric
              icon={<Bot />}
              label={t("hu.home.kpi.conversations")}
              value={n(trend.current)}
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
              trend={{ values: trend.series, ariaLabel: t("hu.home.kpi.conversations.trend") }}
              hint={delta.kind === "none" ? t("hu.home.kpi.delta.none") : t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) })}
              href="/clients"
            />
          ) : null}
          {home?.clients ? (
            <Metric
              icon={<Users />}
              label={t("hu.home.kpi.clients")}
              value={n(home.clients.active)}
              hint={t("hu.home.kpi.clients.hint", { total: n(home.clients.total), provisioning: n(home.clients.provisioning) })}
              href="/clients"
            />
          ) : null}
          {credit && credit.available != null ? (
            <Metric
              icon={<Wallet />}
              label={t("hu.home.kpi.credit")}
              value={formatCompact(credit.available, locale)}
              progress={runwayProgress ?? undefined}
              hint={credit.available === 0 ? t("hu.home.attention.wallet") : runwayProgress ? undefined : t("hu.home.kpi.credit.noSpend")}
              className={credit.available === 0 ? "ring-status-danger/40" : undefined}
              href="/usage"
            />
          ) : null}
          {home?.usage_units ? (
            <Metric
              icon={<MessageSquare />}
              label={t("hu.home.kpi.messages")}
              value={formatCompact(home.usage_units.units, locale)}
              hint={
                home.usage_units.percent != null
                  ? t("hu.home.kpi.messages.cap", { percent: n(home.usage_units.percent), projected: formatCompact(home.usage_units.projected_month_units, locale) })
                  : t("hu.home.kpi.messages.nocap", { projected: formatCompact(home.usage_units.projected_month_units, locale) })
              }
              trend={home.usage_units.daily && home.usage_units.daily.length > 1 ? { values: home.usage_units.daily, ariaLabel: t("hu.home.kpi.messages.trend"), style: "area" } : undefined}
              href="/usage"
            />
          ) : null}
        </section>
        {trend ? (
          <Section title={t("hu.home.chart.title")} className={spend ? "lg:col-span-2" : "lg:col-span-3"}>
            <ConversationsChart trend={trend} />
          </Section>
        ) : null}
      </div>

      {home?.attention && !noClients ? <AttentionBlock attention={home.attention} total={home.clients?.total ?? 0} walletEmpty={credit?.available === 0} t={t} n={n} /> : null}
      <Suspense fallback={<CardSkeleton />}>
        <OnboardingCard principal={principal} />
      </Suspense>
      <Suspense fallback={null}>
        <WorkstationSetup principal={principal} />
      </Suspense>
      {credit && credit.at_risk.length > 0 ? (
        <Section title={t("hu.home.credit.risk.title")}>
          <ul className="divide-y divide-border">
            {credit.at_risk.map((r) => (
              <li key={r.external_client_ref}>
                <Link href={r.href} className="flex items-center justify-between gap-4 py-2 hover:underline">
                  <span className="truncate text-sm font-medium">{r.client_name ?? r.external_client_ref}</span>
                  <span className="shrink-0 text-sm text-status-danger">{t("hu.home.credit.risk.row", { days: n(roundDays(r.days_left)) })}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {hasPortfolio || home?.to_review || activity ? (
        <div className="grid items-start gap-4 lg:grid-cols-3">
          {hasPortfolio ? (
            <Section
              title={t("hu.home.portfolio.title")}
              padded={false}
              className={home?.to_review || activity ? "lg:col-span-2" : "lg:col-span-3"}
              actions={
                <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/clients" />}>
                  {t("hu.home.portfolio.all")}
                </Button>
              }
            >
              <PortfolioTable rows={home!.portfolio!} t={t} n={n} locale={locale} />
            </Section>
          ) : null}
          {home?.to_review || activity ? (
            <div className="flex flex-col gap-4">
              {home?.to_review ? <ReviewBlock review={home.to_review} t={t} n={n} /> : null}
              {activity ? (
                <Section
                  title={t("hu.home.activity.title")}
                  actions={
                    <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/audit" />}>
                      {t("hu.home.activity.all")}
                    </Button>
                  }
                >
                  <ActivityFeed items={activity} locale={locale} empty={t("hu.home.activity.empty")} />
                </Section>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {noClients ? (
        <EmptyState
          title={t("clients.empty.title")}
          description={t("clients.empty.body")}
          action={writeClients ? <Button nativeButton={false} render={<Link href="/clients/new" />}>{t("clients.new")}</Button> : undefined}
          readonly={!writeClients}
        />
      ) : null}
    </>
  );
}
