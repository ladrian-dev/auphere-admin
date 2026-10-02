import { ArrowDownRight, ArrowUpRight, Bot, Users, Wallet } from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, Button, EmptyState, HighlightMetric, Metric, PageHeader, Section, formatCompact, formatNumber } from "@nexus/ui";

import { AttentionBlock } from "@/components/home/attention-block";
import { ConversationsChart } from "@/components/home/conversations-chart";
import { creditRunway, roundDays, trendDelta } from "@/components/home/home-model";
import { SpendCard } from "@/components/home/spend-card";
import { getT } from "@/i18n/server";
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
  const home: Home | null = await api.home().catch(() => null);
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
            <SpendCard spend={spend} t={t} locale={locale} />
          </div>
        ) : null}
        {/* Three cards side by side only where they fit (container query):
            at the pane's narrow widths a cut title says less than a stack. */}
        <section className={spend ? "@container lg:col-span-2" : "@container lg:col-span-3"} aria-label={t("home.title")}>
          <div className="grid gap-4 @xl:grid-cols-3">
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
          </div>
        </section>
        {trend ? (
          <Section title={t("hu.home.chart.title")} className={spend ? "lg:col-span-2" : "lg:col-span-3"}>
            <ConversationsChart trend={trend} />
          </Section>
        ) : null}
      </div>

      {home?.attention && !noClients ? <AttentionBlock attention={home.attention} total={home.clients?.total ?? 0} walletEmpty={credit?.available === 0} t={t} n={n} /> : null}
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
