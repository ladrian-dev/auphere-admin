import { ArrowDownRight, ArrowUpRight, Bot, Plus, Users, Wallet } from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, Button, EmptyState, HighlightMetric, Metric, PageHeader, Section, formatNumber } from "@nexus/ui";

import { AttentionBlock } from "@/components/home/attention-block";
import { ConversationsChart } from "@/components/home/conversations-chart";
import { creditRunway, trendDelta } from "@/components/home/home-model";
import { PartnerPanel } from "@/components/home/partner-panel";
import { SpendCard } from "@/components/home/spend-card";
import { TodayDate } from "@/components/home/today-date";
import { resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor, type Me } from "@/lib/backend";
import type { Home } from "@/lib/backend/home-usage";
import { formatMoneyCompact } from "@/lib/money";
import { LitePanel } from "@/components/lite/lite-panel";
import {
  can,
  requireClientPrincipal,
  requirePartnerModule,
  requirePartnerPrincipal,
  requirePrincipal,
  type PartnerPrincipal,
} from "@/lib/principal";


/**
 * Home (spec 026): what fails, what waits for a person, how the week goes,
 * how long the credit lasts and how each client is doing — from ONE call
 * (`GET /console/home`) plus the last audit entries. Each block is gated by
 * permission on the API and is simply absent when it is `null` or failed.
 */
export default async function HomePage() {
  // Spec 030: la raíz es el Panel de las dos consolas. Una persona de cliente
  // sin módulo Panel va a su primer módulo (requireClientPrincipal).
  const who = await requirePrincipal();
  if (who.kind === "client") return <LitePanel principal={await requireClientPrincipal("panel")} />;
  // Spec 032: a partner without the Panel module lands on its first module.
  await requirePartnerModule("panel");
  return <PartnerHome principal={await requirePartnerPrincipal()} />;
}

async function PartnerHome({ principal }: { principal: PartnerPrincipal }) {
  const { t, locale } = await getT(principal.locale);
  const api = backendFor(principal);
  const [home, me] = await Promise.all([api.home().catch((): Home | null => null), api.me().catch((): Me | null => null)]);
  const readClients = can(principal.role, "clients:read");
  const writeClients = can(principal.role, "clients:write");
  const n = (v: number) => formatNumber(v, locale);

  const trend = home?.conversations_trend ?? null;
  const delta = trend ? trendDelta(trend.current, trend.previous) : null;
  const credit = home?.credit ?? null;
  const spend = home?.spend ?? null;
  const runway = credit ? creditRunway(credit.available_cents, credit.days_left, new Date()) : null;
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

  // Spec 047 (T163, requisito 48): con la consola nueva, el Panel sale del bloque
  // `panel`, y «Necesita tu atención» arregla el saldo en el sitio.
  if (resolveConsoleVersion(me) === "v2" && home?.panel) {
    return (
      <>
        {/* El prototipo aprobado: «Hola, Luis», el partner y el día, y «Nuevo cliente». */}
        <PageHeader
          title={t("home.welcome", { name: principal.name.split(" ")[0] || principal.name })}
          description={
            <span className="flex min-w-0 flex-wrap items-center gap-2">
              <span>{principal.partnerName}</span>
              <span aria-hidden="true">·</span>
              <TodayDate />
            </span>
          }
          size="display"
          actions={
            writeClients ? (
              <Button nativeButton={false} render={<Link href="/clients?new=1" />}>
                <Plus aria-hidden="true" />
                {t("hu.home.newClient")}
              </Button>
            ) : undefined
          }
        />
        {noClients ? (
          // Sin botón: «Nuevo cliente» ya está en la cabecera (un primario por vista).
          <EmptyState title={t("clients.empty.title")} description={t("clients.empty.body")} readonly />
        ) : (
          <PartnerPanel panel={home.panel} trend={trend ? { current: trend.current, previous: trend.previous } : null} />
        )}
      </>
    );
  }

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
          {credit && credit.available_cents != null ? (
            <Metric
              icon={<Wallet />}
              label={t("hu.home.kpi.credit")}
              value={formatMoneyCompact(credit.available_cents, locale)}
              progress={runwayProgress ?? undefined}
              hint={credit.available_cents === 0 ? t("hu.home.attention.wallet") : runwayProgress ? undefined : t("hu.home.kpi.credit.noSpend")}
              className={credit.available_cents === 0 ? "ring-status-danger/40" : undefined}
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

      {home?.attention && !noClients ? <AttentionBlock attention={home.attention} total={home.clients?.total ?? 0} walletEmpty={credit?.available_cents === 0} t={t} n={n} /> : null}

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
