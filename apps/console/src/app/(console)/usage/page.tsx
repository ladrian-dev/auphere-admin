import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert, AlertDescription, Button, EmptyState, Metric, PageHeader, formatDateTime, formatNumber } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { Allocation, Wallet } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";
import { barsFromSeries, cumulativeWithProjection, topMeters } from "@/lib/usage-projection";

import { UsageCharts } from "./charts";
import { UsageControls } from "./controls";

export const metadata = { title: "Consumo" };

type Search = { days?: string; client?: string; source?: string; meter?: string };

const METER_GROUPS: Record<string, string> = { "channel.message": "channel.message", llm: "llm.", media: "media.", voice: "voice." };

const EMPTY_WALLET: Wallet = {
  included_remaining: 0,
  purchased_remaining: 0,
  available: 0,
  reserve: 0,
  included_expires_at: null,
  exhausted: true,
};

export default async function UsagePage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/usage");
  if (!can(principal.role, "usage:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const days = [7, 30, 90].includes(Number(sp.days)) ? Number(sp.days) : 30;
  const meterPrefix = sp.meter && METER_GROUPS[sp.meter] ? METER_GROUPS[sp.meter] : undefined;
  const api = backendFor(principal);
  const [report, series, monthSeries, clients, wallet, allocations] = await Promise.all([
    api.usageV2({ days, client: sp.client, source: sp.source }),
    api.usageSeries({ days, client: sp.client, source: sp.source || "channel", meter: meterPrefix }).catch(() => null),
    api.usageSeries({ days: 31, client: sp.client, source: "channel", meter: "channel.message" }).catch(() => null),
    can(principal.role, "clients:read") ? api.listClients({ limit: 200 }).catch(() => null) : null,
    api.getWallet().catch((): Wallet => EMPTY_WALLET),
    api.listAllocations().catch((): Allocation[] => []),
  ]);
  const n = (v: number) => formatNumber(v, locale);
  const totals = Object.entries(report.totals_by_meter);
  const month = report.month;
  const today = new Date().toISOString().slice(0, 10);
  const names = new Map((clients?.items ?? []).map((c) => [c.external_client_ref, c.name]));

  const { keys, hasOther } = series ? topMeters(series.points) : { keys: [], hasOther: false };
  const bars = series ? barsFromSeries(series.points, keys) : [];
  const barSeries = [...keys.map((k) => ({ key: k, label: k })), ...(hasOther ? [{ key: "other", label: "…" }] : [])];
  const line = monthSeries ? cumulativeWithProjection(monthSeries.points, "channel.message", month.since, month.days_in_month, today) : [];

  const csvHref = `/api/usage/export?days=${days}${sp.client ? `&client=${encodeURIComponent(sp.client)}` : ""}${sp.source ? `&source=${sp.source}` : ""}&lang=${locale}`;
  const bannerKey = month.percent != null && month.percent >= 100 ? "hu.usage.banner.100" : month.percent != null && month.percent >= 80 ? "hu.usage.banner.80" : null;

  return (
    <>
      <PageHeader
        eyebrow={t("nav.group.operate")}
        title={t("usage.title")}
        description={t("usage.description")}
        actions={
          <Button nativeButton={false} variant="outline" size="sm" render={<Link href="/usage/alerts" />}>
            {t("hu.usage.alerts.link")}
          </Button>
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
      <section className="grid gap-4 md:grid-cols-3" aria-label={t("hu.usage.wallet")}>
        <Metric
          label={t("hu.usage.wallet.included")}
          value={n(wallet.included_remaining)}
          hint={
            wallet.included_expires_at
              ? t("hu.usage.wallet.expires", { date: formatDateTime(wallet.included_expires_at, locale) })
              : t("hu.usage.wallet.expires.none")
          }
        />
        <Metric label={t("hu.usage.wallet.purchased")} value={n(wallet.purchased_remaining)} hint={t("hu.usage.wallet.tokens")} />
        <Metric label={t("hu.usage.wallet.reserve")} value={n(wallet.reserve)} hint={t("hu.usage.wallet.reserve.hint")} />
      </section>
      <div className="min-w-0 overflow-x-auto rounded-md ring-1 ring-foreground/10">
        <table className="w-full text-sm">
          <caption className="sr-only">{t("hu.usage.allocations")}</caption>
          <thead>
            <tr className="border-b text-left">
              <th className="h-10 px-2 font-medium">{t("usage.client")}</th>
              <th className="h-10 px-2 text-right font-medium">{t("hu.usage.allocations.cap")}</th>
              <th className="h-10 px-2 text-right font-medium">{t("hu.usage.allocations.remaining")}</th>
            </tr>
          </thead>
          <tbody>
            {allocations.length === 0 ? (
              <tr>
                <td className="p-2 text-muted-foreground" colSpan={3}>
                  {t("hu.usage.allocations.empty")}
                </td>
              </tr>
            ) : (
              allocations.map((row) => (
                <tr key={row.client_ref} className="border-b last:border-0">
                  <td className="max-w-64 truncate p-2" title={names.get(row.client_ref) ?? row.client_ref}>
                    {names.get(row.client_ref) ?? row.client_ref}
                  </td>
                  <td className="p-2 text-right tabular-nums">{n(row.cap)}</td>
                  <td className="p-2 text-right tabular-nums">{n(row.remaining)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
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
            <Metric key={meter} label={meter} value={n(qty)} hint={t("usage.period", { days })} />
          ))}
        </section>
      ) : null}
      {report.buckets.length === 0 ? (
        <EmptyState title={t("usage.empty")} description={t("usage.period", { days })} readonly />
      ) : (
        <div className="min-w-0 overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <table className="w-full text-sm">
            <caption className="sr-only">{t("usage.title")}</caption>
            <thead>
              <tr className="border-b text-left">
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
                  <td className="p-2 font-mono text-xs">{b.meter}</td>
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
    </>
  );
}
