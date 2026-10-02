import Link from "next/link";
import { Suspense } from "react";

import { Alert, AlertDescription, Button, CardSkeleton, EmptyState, Metric, PageHeader, Section, formatCompact, formatNumber } from "@nexus/ui";

import { ActivityFeed } from "@/components/home/activity-feed";
import { AttentionBlock } from "@/components/home/attention-block";
import { ConversationsChart } from "@/components/home/conversations-chart";
import { roundDays, trendDelta } from "@/components/home/home-model";
import { OnboardingCard } from "@/components/home/onboarding-card";
import { PortfolioTable } from "@/components/home/portfolio-table";
import { ReviewBlock } from "@/components/home/review-block";
import { WorkstationSetup } from "@/components/workstation/workstation-setup";
import { getT } from "@/i18n/server";
import type { AuditEntry } from "@/lib/backend";
import { backendFor } from "@/lib/backend";
import type { Home } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";

const DELTA_SIGN = { up: "+", down: "−", same: "=" } as const;
const DELTA_TONE = { up: "positive", down: "negative", same: "neutral" } as const;

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
  const noClients = readClients && home?.clients?.total === 0;

  return (
    <>
      <PageHeader
        eyebrow={principal.partnerName}
        title={t("home.welcome", { name: principal.name })}
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

      {home?.attention && !noClients ? <AttentionBlock attention={home.attention} total={home.clients?.total ?? 0} walletEmpty={credit?.available === 0} t={t} n={n} /> : null}
      <Suspense fallback={<CardSkeleton />}>
        <OnboardingCard principal={principal} />
      </Suspense>
      <Suspense fallback={null}>
        <WorkstationSetup principal={principal} />
      </Suspense>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label={t("home.title")}>
        {trend && delta ? (
          <Metric
            label={t("hu.home.kpi.conversations")}
            value={n(trend.current)}
            delta={
              delta.kind === "none"
                ? undefined
                : {
                    label: `${DELTA_SIGN[delta.kind]}${delta.kind === "same" ? "" : `${n(delta.pct)} %`}`,
                    tone: DELTA_TONE[delta.kind],
                    srLabel: t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) }),
                  }
            }
            trend={{ values: trend.series, ariaLabel: t("hu.home.kpi.conversations.trend") }}
            hint={delta.kind === "none" ? t("hu.home.kpi.delta.none") : t("hu.home.kpi.conversations.hint")}
            href="/clients"
          />
        ) : null}
        {home?.clients ? (
          <Metric
            label={t("hu.home.kpi.clients")}
            value={n(home.clients.active)}
            hint={t("hu.home.kpi.clients.hint", { total: n(home.clients.total), provisioning: n(home.clients.provisioning) })}
            href="/clients"
          />
        ) : null}
        {credit && credit.available != null ? (
          <Metric
            label={t("hu.home.kpi.credit")}
            value={formatCompact(credit.available, locale)}
            hint={
              credit.available === 0
                ? t("hu.home.attention.wallet")
                : credit.days_left != null
                  ? t("hu.home.kpi.credit.days", { days: n(roundDays(credit.days_left)) })
                  : t("hu.home.kpi.credit.noSpend")
            }
            className={credit.available === 0 ? "ring-status-danger/40" : undefined}
            href="/usage"
          />
        ) : null}
        {home?.usage_units ? (
          <Metric
            label={t("hu.home.kpi.messages")}
            value={formatCompact(home.usage_units.units, locale)}
            hint={
              home.usage_units.percent != null
                ? t("hu.home.kpi.messages.cap", { percent: n(home.usage_units.percent), projected: formatCompact(home.usage_units.projected_month_units, locale) })
                : t("hu.home.kpi.messages.nocap", { projected: formatCompact(home.usage_units.projected_month_units, locale) })
            }
            href="/usage"
          />
        ) : null}
      </section>

      {trend || home?.to_review ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {trend ? (
            <Section title={t("hu.home.chart.title")} className="lg:col-span-2">
              <ConversationsChart trend={trend} />
            </Section>
          ) : null}
          {home?.to_review ? <ReviewBlock review={home.to_review} t={t} n={n} /> : null}
        </div>
      ) : null}

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

      {(home?.portfolio && home.portfolio.length > 0) || activity ? (
        <div className="grid gap-4 lg:grid-cols-3">
          {home?.portfolio && home.portfolio.length > 0 ? (
            <Section
              title={t("hu.home.portfolio.title")}
              padded={false}
              className={activity ? "lg:col-span-2" : "lg:col-span-3"}
              actions={
                <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/clients" />}>
                  {t("hu.home.portfolio.all")}
                </Button>
              }
            >
              <PortfolioTable rows={home.portfolio} t={t} n={n} locale={locale} />
            </Section>
          ) : null}
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
