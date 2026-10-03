import Link from "next/link";
import { redirect } from "next/navigation";

import { CircleDollarSign, Users, Wallet as WalletIcon } from "lucide-react";

import { Alert, AlertDescription, Button, EmptyState, Metric, PageHeader, Section, formatNumber } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { Allocation, UsageSpend, Wallet } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";
import { meterLabel } from "@/lib/meter-label";
import { formatMoney } from "@/lib/money";
import { barsFromSeries, cumulativeWithProjection, topMeters } from "@/lib/usage-projection";

import { BalanceTable } from "./balance-table";
import { BuyDialog } from "./buy-dialog";
import { UsageCharts } from "./charts";
import { UsageControls } from "./controls";
import { SpendChart } from "./spend-chart";
import { SpendControls } from "./spend-controls";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.usage");

type Search = { days?: string; client?: string; source?: string; meter?: string };

const METER_GROUPS: Record<string, string> = { "channel.message": "channel.message", llm: "llm.", media: "media.", voice: "voice." };

// When the ledger cannot be read the page says so; it never paints "0 %"
// or "exhausted", which would be a lie a partner acts on (buys credit).
const UNREADABLE_WALLET: Wallet = {
  included_remaining_cents: 0,
  purchased_remaining_cents: 0,
  available_cents: 0,
  reserve_cents: 0,
  included_expires_at: null,
  exhausted: false,
};

export default async function UsagePage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/usage");
  if (!can(principal.role, "usage:read")) redirect("/");
  const canWrite = can(principal.role, "usage:write");
  // Spec 005: la compra de crédito **sí** existe en producción — es un pago
  // real. La condición vieja la escondía allí porque el endpoint que había
  // detrás respondía 404 en prod: acreditarse saldo sin pagar era un juguete
  // de desarrollo. Y el permiso es el de facturación, no el de escribir
  // consumo: quien compra es quien paga.
  const canBuyCredit = can(principal.role, "billing:manage");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const days = [7, 30, 90].includes(Number(sp.days)) ? Number(sp.days) : 30;
  const meterPrefix = sp.meter && METER_GROUPS[sp.meter] ? METER_GROUPS[sp.meter] : undefined;
  const api = backendFor(principal);
  const [report, series, monthSeries, clients, walletRead, allocations] = await Promise.all([
    api.usageV2({ days, client: sp.client, source: sp.source }),
    api.usageSeries({ days, client: sp.client, source: sp.source || "channel", meter: meterPrefix }).catch(() => null),
    api.usageSeries({ days: 31, client: sp.client, source: "channel", meter: "channel.message" }).catch(() => null),
    can(principal.role, "clients:read") ? api.listClients({ limit: 200 }).catch(() => null) : null,
    api.getWallet().then((w) => ({ ok: true as const, wallet: w })).catch(() => ({ ok: false as const, wallet: UNREADABLE_WALLET })),
    api.listAllocations().catch((): Allocation[] => []),
  ]);
  // Spec 028: the money half of the page. ``null`` = the ledger could not be
  // read; the cards and the chart then say so instead of painting zeros.
  const spend: UsageSpend | null = await api.usageSpend({ days, client: sp.client }).catch(() => null);
  const spendMonth: UsageSpend | null = sp.client ? await api.usageSpend({ days: 7 }).catch(() => null) : spend;
  const wallet = walletRead.wallet;
  const walletUnreadable = !walletRead.ok;
  const n = (v: number) => formatNumber(v, locale);
  const money = (cents: number) => formatMoney(cents, locale);
  const totals = Object.entries(report.totals_by_meter);
  const month = report.month;
  const today = new Date().toISOString().slice(0, 10);
  const names = new Map((clients?.items ?? []).map((c) => [c.external_client_ref, c.name]));

  const { keys, hasOther } = series ? topMeters(series.points) : { keys: [], hasOther: false };
  const bars = series ? barsFromSeries(series.points, keys) : [];
  const barSeries = [...keys.map((k) => ({ key: k, label: meterLabel(k, t) })), ...(hasOther ? [{ key: "other", label: "…" }] : [])];
  const line = monthSeries ? cumulativeWithProjection(monthSeries.points, "channel.message", month.since, month.days_in_month, today) : [];

  const csvHref = `/api/usage/export?days=${days}${sp.client ? `&client=${encodeURIComponent(sp.client)}` : ""}${sp.source ? `&source=${sp.source}` : ""}&lang=${locale}`;
  const bannerKey = month.percent != null && month.percent >= 100 ? "hu.usage.banner.100" : month.percent != null && month.percent >= 80 ? "hu.usage.banner.80" : null;
  const allocatedRefs = new Set(allocations.map((row) => row.client_ref));
  const everyone = (clients?.items ?? []).map((c) => ({ ref: c.external_client_ref, name: c.name }));
  const unassigned = everyone.filter((c) => !allocatedRefs.has(c.ref));
  const monthOf = new Map((spendMonth?.month_by_client ?? []).map((m) => [m.external_client_ref, m.cents]));
  const balanceRows = allocations.map((row) => ({
    ref: row.client_ref,
    name: names.get(row.client_ref) ?? row.client_ref,
    capCents: row.cap_cents,
    remainingCents: row.remaining_cents,
    monthCents: monthOf.get(row.client_ref) ?? 0,
  }));
  const assignedCents = Math.max(0, wallet.available_cents - wallet.reserve_cents);

  return (
    <>
      <PageHeader
        eyebrow={t("nav.group.operate")}
        title={t("usage.title")}
        description={t("usage.description")}
        actions={
          <>
            <Button nativeButton={false} variant="outline" size="sm" render={<Link href="/usage/alerts" />}>
              {t("hu.usage.alerts.link")}
            </Button>
            {canBuyCredit ? <BuyDialog /> : null}
          </>
        }
      />
      {bannerKey ? (
        <Alert variant={bannerKey === "hu.usage.banner.100" ? "destructive" : "default"} role="alert">
          <AlertDescription className="flex flex-wrap items-center gap-2">
            <span>{t(bannerKey, { percent: n(month.percent ?? 0), used: n(month.units), cap: n(month.cap ?? 0) })}</span>
            <Link href="/usage/alerts" className="underline">
              {t("hu.usage.banner.manage")}
            </Link>
          </AlertDescription>
        </Alert>
      ) : null}
      {walletUnreadable ? (
        <Alert>
          <AlertDescription>{t("hu.usage.wallet.unreadable")}</AlertDescription>
        </Alert>
      ) : null}

      {/* Spec 028 · 1. El saldo de un vistazo: disponible, asignado y gasto. */}
      <section className="grid gap-4 md:grid-cols-3" aria-label={t("hu.usage.wallet")}>
        <Metric
          icon={<WalletIcon />}
          label={t("hu.usage.card.available")}
          value={walletUnreadable ? "—" : money(wallet.available_cents)}
          hint={walletUnreadable ? t("hu.usage.wallet.unreadable.hint") : t("hu.usage.card.available.hint", { included: money(wallet.included_remaining_cents), purchased: money(wallet.purchased_remaining_cents) })}
        />
        <Metric
          icon={<Users />}
          label={t("hu.usage.card.assigned")}
          value={walletUnreadable ? "—" : money(assignedCents)}
          progress={!walletUnreadable && wallet.available_cents > 0 ? { value: assignedCents, max: wallet.available_cents, label: t("hu.usage.card.assigned"), tone: "positive" } : undefined}
          hint={
            walletUnreadable
              ? undefined
              : wallet.reserve_cents >= 0
                ? t("hu.usage.card.assigned.hint", { amount: money(wallet.reserve_cents) })
                : t("hu.usage.card.assigned.over", { amount: money(-wallet.reserve_cents) })
          }
        />
        <Metric
          icon={<CircleDollarSign />}
          label={t("hu.usage.card.month")}
          value={spendMonth ? money(spendMonth.month_cents) : "—"}
          hint={!spendMonth ? t("hu.usage.spend.unreadable") : spendMonth.month_cents > 0 ? t("hu.usage.card.month.hint", { amount: money(spendMonth.projected_cents) }) : t("hu.usage.card.month.none")}
        />
      </section>

      {/* 2. Saldo por cliente: sin campos en la tabla, las acciones en «⋯». */}
      <Section title={t("hu.usage.balance.title")} padded={false}>
        <BalanceTable rows={balanceRows} unassigned={unassigned} everyone={everyone} canWrite={canWrite} exhausted={!walletUnreadable && wallet.exhausted} />
      </Section>

      {/* 3. Gasto por día, en dólares. */}
      <Section id="gasto" title={t("hu.usage.spend.title")} actions={<SpendControls days={days} client={sp.client ?? ""} clients={everyone} />}>
        {spend ? <SpendChart spend={spend} /> : <p className="py-8 text-center text-sm text-muted-foreground">{t("hu.usage.spend.unreadable")}</p>}
      </Section>

      {/* 4. El detalle técnico, plegado: lo que mide la plataforma por dentro. */}
      <details className="group rounded-md bg-card ring-1 ring-foreground/10">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 p-4 text-sm font-medium">
          <span>
            {t("hu.usage.detail.title")}
            <span className="block text-xs font-normal text-muted-foreground">{t("hu.usage.detail.hint")}</span>
          </span>
          <span aria-hidden="true" className="text-muted-foreground transition-transform group-open:rotate-90">
            ›
          </span>
        </summary>
        <div className="flex flex-col gap-4 border-t border-border p-4">
      <UsageControls
        days={days}
        client={sp.client ?? ""}
        source={sp.source ?? ""}
        meter={sp.meter ?? ""}
        clients={clients?.items.map((c) => ({ ref: c.external_client_ref, name: c.name })) ?? []}
        csvHref={csvHref}
      />
      <section className="grid gap-4 md:grid-cols-3" aria-label={t("hu.usage.month")}>
        <Metric label={t("hu.usage.month.units")} value={n(month.units)} hint={month.cap != null ? `${t("hu.usage.month.cap")}: ${n(month.cap)}` : t("hu.usage.month.nocap")} />
        <Metric label={t("hu.usage.month.projection")} value={n(month.projected_month_units)} hint={t("hu.usage.month.basis", { days: month.basis_days, total: month.days_in_month })} />
        <Metric label={t("hu.usage.month.cap")} value={month.percent != null ? t("hu.usage.month.percent", { percent: n(month.percent) }) : "—"} hint={month.cap != null ? n(month.cap) : t("hu.usage.month.nocap")} href="/usage/alerts" />
      </section>
      <UsageCharts bars={bars} barSeries={barSeries} line={line} cap={month.cap} monthUnits={month.units} percent={month.percent} />
      {report.unpriced_records > 0 ? <p className="text-sm text-muted-foreground">{t("hu.usage.unpriced", { count: n(report.unpriced_records) })}</p> : null}
      {totals.length > 0 ? (
        <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-4" aria-label={t("usage.totals")}>
          {totals.map(([meter, qty]) => (
            <Metric key={meter} label={meterLabel(meter, t)} value={n(qty)} hint={t("usage.period", { days })} />
          ))}
        </section>
      ) : null}
      {report.buckets.length === 0 ? (
        <EmptyState title={t("usage.empty")} description={t("usage.period", { days })} readonly />
      ) : (
        <div className="max-h-112 min-w-0 overflow-auto rounded-md ring-1 ring-foreground/10">
          <table className="w-full text-sm">
            <caption className="sr-only">{t("usage.title")}</caption>
            <thead>
              <tr className="sticky top-0 border-b bg-card text-left">
                <th className="h-10 px-2 font-medium">{t("usage.client")}</th>
                <th className="h-10 px-2 font-medium">{t("usage.meter")}</th>
                <th className="h-10 px-2 font-medium">{t("usage.source")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("usage.quantity")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("usage.billable")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("usage.records")}</th>
              </tr>
            </thead>
            <tbody>
              {report.buckets.map((b, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="max-w-64 truncate p-2" title={b.client_name ?? b.external_client_ref ?? ""}>
                    {b.client_name ?? b.external_client_ref ?? "—"}
                  </td>
                  <td className="p-2" title={b.meter}>{meterLabel(b.meter, t)}</td>
                  <td className="p-2">{t(`usage.source.${b.source}` as "usage.source.channel")}</td>
                  <td className="p-2 text-right tabular-nums">{n(b.quantity)}</td>
                  <td className="p-2 text-right tabular-nums">{b.source === "qa" ? "—" : n(b.billable_qty)}</td>
                  <td className="p-2 text-right tabular-nums">{n(b.records)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
        </div>
      </details>
    </>
  );
}
