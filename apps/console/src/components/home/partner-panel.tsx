"use client";

import { ArrowDown, ArrowRight, ArrowUp, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { BlockChart, Button, Card, CardContent, cn, formatNumber } from "@nexus/ui";

import { attentionKey, isPartnerRow } from "@/components/attention/attention-model";
import { AttentionRow } from "@/components/attention/attention-row";
import { BuyDialog } from "@/app/(console)/usage/buy-dialog";
import { BuildExtensionButton } from "@/components/attention/build-extension-button";
import { moneyText } from "@/components/money/money-model";
import { useLocale, useT } from "@/i18n/client";
import type { HomePanel, PanelAttention } from "@/lib/backend/home-usage";
import type { BuildBudget } from "@/lib/backend/money-types";

import { trendDelta } from "./home-model";
import { conversationColumns, conversationTotal, failed, monthPeriod, shareLabel } from "./panel-model";

/** Los colores de las partes del gasto: las series de las gráficas y, después, tonos del mismo sistema. */
const SERIES = ["bg-series-1", "bg-series-2", "bg-accent-mid", "bg-muted-foreground/50", "bg-muted-foreground/25"];

/**
 * El Panel del partner con la consola nueva (spec 047, T163, requisito 48), con
 * la composición del prototipo aprobado («Consola de partners v2»): a la
 * izquierda el gasto del mes repartido por cliente; a la derecha tres cifras
 * (conversaciones de la semana, clientes atendiendo y saldo disponible) y debajo
 * las conversaciones por día en bloques, con su tabla; al final, lo que necesita
 * su atención, con su arreglo en el sitio cuando se puede. Cada bloque dice su
 * periodo. Sin cuerpos de mensaje: solo cifras y nombres.
 */
export function PartnerPanel({
  panel,
  trend = null,
  buildBudget = null,
  canBuy = false,
}: {
  panel: HomePanel;
  trend?: { current: number; previous: number | null } | null;
  /** Spec 072 (3.4): el tope de construcción, para su línea aunque vaya por debajo del 80 %. */
  buildBudget?: BuildBudget | null;
  /** Quien puede comprar saldo (`billing:manage`) lo recarga desde «Saldo disponible» (owner, 2026-11-22). */
  canBuy?: boolean;
}) {
  const t = useT();
  const locale = useLocale();
  const n = (v: number) => formatNumber(v, locale);
  const { spend, clients, balance, conversations_per_day: daily, attention } = panel;
  const flagged = new Set((attention ?? []).filter((row) => !isPartnerRow(row)).map((row) => row.external_client_ref)).size;
  // Spec 071 (4.2, 4.3): la cuenta y el tope de construcción se ven en sus cifras, no solo en la lista.
  const account = (attention ?? []).find((row) => row.code === "account_empty" || row.code === "account_low") ?? null;
  const build = (attention ?? []).find((row) => row.code === "build_cap_exhausted" || row.code === "build_cap_warning") ?? null;

  return (
    <div className="grid min-w-0 gap-6" data-slot="partner-panel">
      {panel.errors.length ? (
        <p role="status" className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-pretty text-muted-foreground">
          {t("panel.v2.partial")}
        </p>
      ) : null}

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2.6fr)]">
        {spend ? (
          <Card className="xl:row-span-2">
            <CardContent className="grid min-w-0 content-start gap-3" data-slot="panel-spend">
              <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <h2 className="text-base font-semibold">{t("panel.v2.spend.title")}</h2>
                <Link href="/usage" className="inline-flex items-center gap-1 text-sm font-medium underline-offset-4 hover:underline">
                  {t("panel.v2.spend.more")}
                  <ArrowRight aria-hidden="true" className="size-4" />
                </Link>
              </div>
              <div className="grid gap-1">
                <p className="text-4xl font-semibold tracking-tight tabular-nums">{moneyText(spend.total)}</p>
                <p className="text-xs text-muted-foreground" data-slot="panel-period">
                  {monthPeriod(t, spend.since, spend.until)}
                </p>
              </div>
              {spend.shares.length ? (
                <>
                  <div
                    className="flex h-3 w-full gap-px overflow-hidden rounded-full bg-muted"
                    role="img"
                    aria-label={`${t("panel.v2.spend.split")}: ${spend.shares.map((s) => `${shareLabel(t, s)} ${moneyText(s.amount)}`).join(", ")}`}
                  >
                    {spend.shares.map((s, i) => (
                      <span key={`${s.kind}-${s.external_client_ref ?? s.line ?? i}`} className={SERIES[i % SERIES.length]} style={{ width: `${sharePct(s.amount.amount_micros, spend.total.amount_micros)}%` }} />
                    ))}
                  </div>
                  <ul className="grid min-w-0 gap-2 text-sm" aria-hidden="true">
                    {spend.shares.map((s, i) => (
                      <li key={`${s.kind}-${s.external_client_ref ?? s.line ?? i}`} className="flex min-w-0 items-center gap-2">
                        <span className={`size-2 shrink-0 rounded-sm ${SERIES[i % SERIES.length]}`} />
                        <span className="min-w-0 flex-1 text-pretty break-words" title={shareLabel(t, s)}>
                          {shareLabel(t, s)}
                        </span>
                        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{`${n(Math.round(sharePct(s.amount.amount_micros, spend.total.amount_micros)))} %`}</span>
                        <span className="shrink-0 font-medium tabular-nums">
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
              <BuildLine row={build} budget={buildBudget} />
            </CardContent>
          </Card>
        ) : null}

        <div className="grid min-w-0 gap-4 md:grid-cols-3">
          {daily ? (
            <Card>
              <CardContent className="grid min-w-0 content-start gap-2" data-slot="panel-count">
                <h2 className="text-xs text-muted-foreground">{t("panel.v2.count.title")}</h2>
                <div className="flex min-w-0 items-end justify-between gap-3">
                  <p className="text-[28px] leading-tight font-semibold tracking-tight tabular-nums">{n(conversationTotal(daily))}</p>
                  <Sparkline values={daily.resolved_without_person.map((v, i) => v + (daily.handed_to_person[i] ?? 0))} />
                </div>
                <TrendLine trend={trend} />
              </CardContent>
            </Card>
          ) : null}
          {clients ? (
            <Card>
              <CardContent className="grid min-w-0 content-start gap-2" data-slot="panel-clients">
                <h2 className="text-xs text-muted-foreground">{t("panel.v2.clients.servingTitle")}</h2>
                <p className="text-[28px] leading-tight font-semibold tracking-tight tabular-nums">{n(clients.serving)}</p>
                <p className="text-sm text-muted-foreground">
                  {clients.onboarding > 0
                    ? t("panel.v2.clients.ofOnboarding", { total: n(clients.not_archived), n: n(clients.onboarding) })
                    : t("panel.v2.clients.of", { total: n(clients.not_archived) })}
                </p>
              </CardContent>
            </Card>
          ) : null}
          {balance ? (
            <Card>
              <CardContent className="grid min-w-0 content-start gap-2" data-slot="panel-balance">
                <h2 className="text-xs text-muted-foreground">{t("money.figure.available")}</h2>
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2">
                  <p className="text-[28px] leading-tight font-semibold tracking-tight tabular-nums">{moneyText(balance.available, "down")}</p>
                  {canBuy ? <BuyDialog accountCurrency={balance.available.currency} variant="outline" size="sm" label={t("panel.v2.balance.topUp")} /> : null}
                </div>
                {/* Spec 072 (2.5): la barra es lo disponible, como dice la cifra de encima. */}
                <div
                  className="h-2 w-full overflow-hidden rounded-full bg-muted"
                  role="meter"
                  aria-label={t("panel.v2.balance.meter", { amount: moneyText(balance.available, "down") })}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(sharePct(balance.available.amount_micros, balance.in_bags.amount_micros + balance.available.amount_micros))}
                  data-slot="panel-balance-bar"
                >
                  <span
                    className="block h-full rounded-full bg-primary"
                    style={{ width: `${sharePct(balance.available.amount_micros, balance.in_bags.amount_micros + balance.available.amount_micros)}%` }}
                  />
                </div>
                <p className="text-sm text-muted-foreground">
                  {t("panel.v2.balance.assigned", { amount: `${balance.in_bags_approx ? `${t("money.approxPrefix")} ` : ""}${moneyText(balance.in_bags, "down")}` })}
                </p>
                {account ? (
                  <p
                    className={`flex items-center gap-2 text-sm font-medium ${account.code === "account_empty" ? "text-status-danger-text" : "text-status-warning-text"}`}
                    data-slot="panel-balance-state"
                  >
                    <span aria-hidden="true" className={`size-2 rounded-full ${account.code === "account_empty" ? "bg-status-danger" : "bg-status-warning"}`} />
                    {t(account.code === "account_empty" ? "att.panel.balance.empty" : "att.panel.balance.low")}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>

        {daily ? (
          <Card>
            <CardContent className="relative grid min-w-0 gap-3 overflow-x-clip" data-slot="panel-conversations">
              <BlockTitle title={t("panel.v2.conversations.title")} period={t("panel.v2.period.7d")} />
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

      <Attention
        rows={attention}
        allServing={panel.all_serving}
        unreadable={failed(panel, "attention")}
        healthy={clients ? { ok: Math.max(0, clients.not_archived - flagged), total: clients.not_archived } : null}
      />
    </div>
  );
}

/** El porcentaje de una parte sobre el total; 0 sin total. */
function sharePct(part: number, total: number): number {
  return total > 0 ? Math.min(100, Math.max(0, (part / total) * 100)) : 0;
}

/** La línea de las conversaciones de la semana, decorativa: la cifra y la gráfica de abajo dicen lo mismo. */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const max = Math.max(1, ...values);
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 120},${36 - (v / max) * 32}`).join(" ");
  return (
    <svg viewBox="0 0 120 40" className="h-10 w-28 shrink-0 text-primary" aria-hidden="true" focusable="false">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
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
function Attention({
  rows,
  allServing,
  unreadable,
  healthy,
}: {
  rows: PanelAttention[] | null;
  allServing: boolean;
  unreadable: boolean;
  healthy: { ok: number; total: number } | null;
}) {
  const t = useT();
  // Como el prototipo: se ven las cuatro más graves y el resto con «Ver N más».
  const [all, setAll] = React.useState(false);
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
        {/* Spec 071 (4.4): la lista ya no es solo de clientes. */}
        <p className="text-sm">{allServing ? t("att.none") : t("panel.v2.attention.none")}</p>
      </div>
    );
  }
  return (
    <section aria-labelledby="panel-attention-h" className="grid min-w-0 rounded-md bg-card ring-1 ring-foreground/10" data-slot="panel-attention">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border px-4 py-3">
        <h2 id="panel-attention-h" className="flex items-center gap-2 text-base font-semibold">
          {t("hu.home.attention.title")}
          <span className="rounded-full bg-status-danger-bg px-2 text-xs font-medium text-status-danger-text tabular-nums">{rows.length}</span>
        </h2>
        {healthy ? <p className="text-xs text-muted-foreground">{t("panel.v2.attention.healthy", { ok: healthy.ok, total: healthy.total })}</p> : null}
      </div>
      <ul className="divide-y divide-border px-4">
        {(all ? rows : rows.slice(0, SHOWN)).map((row) => (
          <AttentionRow key={attentionKey(row)} row={row} />
        ))}
      </ul>
      {rows.length > SHOWN ? (
        <Button type="button" variant="link" size="sm" className="mx-4 mb-3 justify-self-start px-0" onClick={() => setAll((v) => !v)}>
          {all ? t("panel.v2.attention.less") : t("panel.v2.attention.rest", { n: rows.length - SHOWN })}
        </Button>
      ) : null}
    </section>
  );
}

const SHOWN = 4;

/** «↑ 28 % más que los 7 días anteriores» en verde, o «↓ … menos …» en ámbar (prototipo). */
function TrendLine({ trend }: { trend: { current: number; previous: number | null } | null }) {
  const t = useT();
  const locale = useLocale();
  const delta = trend ? trendDelta(trend.current, trend.previous) : null;
  if (!delta || delta.kind === "none") {
    return (
      <p className="text-xs text-muted-foreground" data-slot="panel-period">
        {t("panel.v2.period.7d")}
      </p>
    );
  }
  const pct = formatNumber(delta.pct, locale);
  return (
    <p
      className={`inline-flex items-center gap-1 text-[13px] ${delta.kind === "down" ? "text-warning" : "text-status-positive-text"}`}
      data-slot="panel-period"
    >
      {delta.kind === "up" ? <ArrowUp aria-hidden="true" className="size-3 shrink-0" /> : delta.kind === "down" ? <ArrowDown aria-hidden="true" className="size-3 shrink-0" /> : null}
      {t(`hu.home.kpi.delta.${delta.kind}`, { pct })}
    </p>
  );
}

/**
 * «Construcción y pruebas» bajo las partes del gasto — spec 072 (3.4). Siempre
 * que se pueda leer el tope: neutra por debajo del 80 % («la paga Auphere hasta
 * el tope»); desde el 80 %, la línea de la 071 en ámbar (rojo al 100 %) con
 * «Pedir ampliación».
 */
function BuildLine({ row, budget }: { row: PanelAttention | null; budget: BuildBudget | null }) {
  const t = useT();
  const flagged = row?.data?.spent && row.data.cap && row.data.pct != null ? row : null;
  const spent = flagged?.data?.spent ?? budget?.spent ?? null;
  const cap = flagged?.data?.cap ?? budget?.cap ?? null;
  if (!spent || !cap) return null;
  const pct = flagged?.data?.pct ?? (cap.amount_micros > 0 ? Math.round((spent.amount_micros / cap.amount_micros) * 100) : 0);
  const tone = !flagged ? "calm" : flagged.code === "build_cap_exhausted" ? "danger" : "warn";
  return (
    <div className="mt-1 grid gap-2 border-t border-border pt-3" data-slot="panel-build" data-code={flagged?.code ?? "build_cap_ok"} data-tone={tone}>
      <p className={cn("text-sm", tone === "danger" ? "text-status-danger-text" : tone === "warn" ? "text-status-warning-text" : "text-muted-foreground")}>
        {tone === "calm"
          ? t("att.panel.buildCalm", { spent: moneyText(spent), cap: moneyText(cap) })
          : t("att.panel.build", { spent: moneyText(spent), cap: moneyText(cap), pct })}
      </p>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-label={t("att.title.build")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, pct)}
      >
        <span
          className={cn("block h-full rounded-full", tone === "danger" ? "bg-status-danger" : tone === "warn" ? "bg-status-warning" : "bg-muted-foreground/40")}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      {tone !== "calm" ? <BuildExtensionButton /> : null}
    </div>
  );
}
