"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import Link from "next/link";

import { BlockChart, Button, Card, CardContent, formatNumber } from "@nexus/ui";

import { reasonText } from "@/components/clients/v2/client-v2-model";
import { BalanceButton } from "@/components/money/balance-button";
import { moneyText } from "@/components/money/money-model";
import { clientHref } from "@/components/shell/routes-v2";
import { useLocale, useT } from "@/i18n/client";
import type { HomePanel, PanelAttention } from "@/lib/backend/home-usage";

import { attentionFix, conversationColumns, conversationTotal, failed, monthPeriod, shareLabel } from "./panel-model";

/** Los colores de las partes del gasto: las series de las gráficas y, después, tonos del mismo sistema. */
const SERIES = ["bg-series-1", "bg-series-2", "bg-accent-mid", "bg-muted-foreground/50", "bg-muted-foreground/25"];

/**
 * El Panel del partner con la consola nueva (spec 047, T163, requisito 48): lo
 * que necesita su atención, con su arreglo en el sitio cuando se puede (el saldo
 * se asigna o se pide aquí mismo); el gasto del mes repartido; sus clientes; su
 * saldo; y las conversaciones de los últimos 7 días en bloques, con su tabla.
 * Cada bloque dice su periodo. Sin cuerpos de mensaje: solo cifras y nombres.
 */
export function PartnerPanel({ panel }: { panel: HomePanel }) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const { spend, clients, balance, conversations_per_day: daily, attention } = panel;

  return (
    <div className="grid min-w-0 gap-6" data-slot="partner-panel">
      {panel.errors.length ? (
        <p role="status" className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-pretty text-muted-foreground">
          {t("panel.v2.partial")}
        </p>
      ) : null}

      <Attention rows={attention} allServing={panel.all_serving} unreadable={failed(panel, "attention")} />

      <div className="grid min-w-0 gap-4 lg:grid-cols-3">
        {spend ? (
          <Card className="lg:col-span-2">
            <CardContent className="grid min-w-0 gap-3" data-slot="panel-spend">
              <BlockTitle title={t("panel.v2.spend.title")} period={monthPeriod(t, spend.since, spend.until)} />
              <p className="text-2xl font-semibold tabular-nums">{moneyText(spend.total)}</p>
              {spend.shares.length ? (
                <>
                  <div
                    className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
                    role="img"
                    aria-label={`${t("panel.v2.spend.split")}: ${spend.shares.map((s) => `${shareLabel(t, s)} ${moneyText(s.amount)}`).join(", ")}`}
                  >
                    {spend.shares.map((s, i) => {
                      const pct = spend.total.amount_micros > 0 ? (s.amount.amount_micros / spend.total.amount_micros) * 100 : 0;
                      return <span key={`${s.kind}-${s.external_client_ref ?? s.line ?? i}`} className={SERIES[i % SERIES.length]} style={{ width: `${pct}%` }} />;
                    })}
                  </div>
                  <ul className="grid min-w-0 gap-1 text-sm" aria-hidden="true">
                    {spend.shares.map((s, i) => (
                      <li key={`${s.kind}-${s.external_client_ref ?? s.line ?? i}`} className="flex min-w-0 items-center gap-2">
                        <span className={`size-2 shrink-0 rounded-full ${SERIES[i % SERIES.length]}`} />
                        <span className="min-w-0 flex-1 truncate">{shareLabel(t, s)}</span>
                        <span className="shrink-0 tabular-nums">
                          {s.approx ? `${t("money.approxPrefix")} ` : ""}
                          {moneyText(s.amount)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t("panel.v2.spend.none")}</p>
              )}
              <Link href="/usage" className="w-fit text-sm font-medium text-primary-text underline-offset-4 hover:underline">
                {t("panel.v2.spend.more")}
              </Link>
            </CardContent>
          </Card>
        ) : null}

        <div className="grid min-w-0 gap-4">
          {clients ? (
            <Card>
              <CardContent className="grid min-w-0 gap-2" data-slot="panel-clients">
                <BlockTitle title={t("panel.v2.clients.title")} period={t("panel.v2.period.now")} />
                <p className="text-2xl font-semibold tabular-nums">{t("panel.v2.clients.serving", { serving: n(clients.serving), total: n(clients.not_archived) })}</p>
                {clients.onboarding > 0 ? <p className="text-sm text-muted-foreground">{t("panel.v2.clients.onboarding", { n: n(clients.onboarding) })}</p> : null}
              </CardContent>
            </Card>
          ) : null}
          {balance ? (
            <Card>
              <CardContent className="grid min-w-0 gap-2" data-slot="panel-balance">
                <BlockTitle title={t("panel.v2.balance.title")} period={t("panel.v2.period.now")} />
                <dl className="grid min-w-0 grid-cols-2 gap-3">
                  <div className="grid min-w-0 gap-1">
                    <dt className="text-xs text-muted-foreground">{t("money.figure.available")}</dt>
                    <dd className="text-lg font-semibold tabular-nums">{moneyText(balance.available, "down")}</dd>
                  </div>
                  <div className="grid min-w-0 gap-1">
                    <dt className="text-xs text-muted-foreground">{t("money.figure.inBags")}</dt>
                    <dd className="text-lg font-semibold tabular-nums">
                      {balance.in_bags_approx ? `${t("money.approxPrefix")} ` : ""}
                      {moneyText(balance.in_bags, "down")}
                    </dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>

      {daily ? (
        <Card>
          <CardContent className="relative grid min-w-0 gap-3 overflow-x-clip" data-slot="panel-conversations">
            <BlockTitle title={t("panel.v2.conversations.title")} period={t("panel.v2.period.7d")} />
            <p className="text-sm text-muted-foreground">{t("panel.v2.conversations.total", { n: n(conversationTotal(daily)) })}</p>
            <BlockChart
              title={t("panel.v2.conversations.title")}
              series={[
                { key: "resolved", label: t("panel.v2.conversations.resolved") },
                { key: "handed", label: t("panel.v2.conversations.handed") },
              ]}
              columns={conversationColumns(t, daily)}
              locale={locale}
              copy={{
                column: t("money.chart.day"),
                total: t("money.chart.columnTotal"),
                top: t("money.chart.top"),
                noData: t("money.chart.noData"),
                empty: t("panel.v2.conversations.empty"),
                totalOf: (formatted) => t("panel.v2.conversations.of", { n: formatted }),
              }}
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function BlockTitle({ title, period }: { title: string; period: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="text-xs text-muted-foreground" data-slot="panel-period">
        {period}
      </p>
    </div>
  );
}

/** «Necesita tu atención» (48.2): lo más grave primero (el orden lo pone la API), con su arreglo. */
function Attention({ rows, allServing, unreadable }: { rows: PanelAttention[] | null; allServing: boolean; unreadable: boolean }) {
  const t = useT();
  if (unreadable) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        {t("panel.v2.attention.error")}
      </p>
    );
  }
  if (!rows || rows.length === 0) {
    return (
      <div className="flex items-center gap-3 rounded-md bg-card px-4 py-3 ring-1 ring-foreground/10" role="status" data-slot="panel-all-serving">
        <CheckCircle2 aria-hidden="true" className="size-5 shrink-0 text-status-positive" />
        <p className="text-sm">{allServing ? t("panel.v2.allServing") : t("panel.v2.attention.none")}</p>
      </div>
    );
  }
  return (
    <section aria-labelledby="panel-attention-h" className="grid min-w-0 gap-2 rounded-md bg-card p-4 ring-1 ring-status-danger/30" data-slot="panel-attention">
      <h2 id="panel-attention-h" className="flex items-center gap-2 text-base font-semibold">
        <AlertTriangle aria-hidden="true" className="size-4 text-status-danger" />
        {t("hu.home.attention.title")}
        <span className="rounded-full bg-status-danger/15 px-2 text-xs tabular-nums">{rows.length}</span>
      </h2>
      <ul className="divide-y divide-border">
        {rows.map((row) => {
          const name = row.client_name ?? row.external_client_ref;
          const fix = attentionFix(row);
          return (
            <li key={`${row.external_client_ref}-${row.code}`} className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 py-2" data-code={row.code}>
              <div className="flex min-w-0 flex-1 flex-col">
                <Link href={clientHref(row.external_client_ref)} className="truncate text-sm font-medium hover:underline">
                  {name}
                </Link>
                <span className="text-sm text-pretty text-muted-foreground">{reasonText(t, row.code, row.count, null)}</span>
              </div>
              {fix.kind === "link" ? (
                <Button size="sm" variant="outline" nativeButton={false} render={<Link href={fix.href} />}>
                  {t(fix.label)}
                </Button>
              ) : (
                <BalanceButton refId={row.external_client_ref} name={name} mode={fix.kind} />
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
