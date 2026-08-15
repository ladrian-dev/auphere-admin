import { redirect } from "next/navigation";

import { EmptyState, Metric, PageHeader, formatNumber } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { UsageControls } from "./controls";

export const metadata = { title: "Consumo" };

type Search = { days?: string; client?: string; source?: string };

export default async function UsagePage({ searchParams }: { searchParams: Promise<Search> }) {
  const principal = await requirePrincipal("/usage");
  if (!can(principal.role, "usage:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const days = [7, 30, 90].includes(Number(sp.days)) ? Number(sp.days) : 30;
  const api = backendFor(principal);
  const [report, clients] = await Promise.all([
    api.usage({ days, client: sp.client, source: sp.source }),
    can(principal.role, "clients:read") ? api.listClients({ limit: 200 }).catch(() => null) : null,
  ]);
  const totals = Object.entries(report.totals_by_meter);
  const csv = [
    ["client_ref", "client_name", "meter", "source", "quantity", "billable_qty", "records"].join(","),
    ...report.buckets.map((b) => [b.external_client_ref, b.client_name, b.meter, b.source, b.quantity, b.billable_qty, b.records].map((v) => JSON.stringify(v ?? "")).join(",")),
  ].join("\n");

  return (
    <>
      <PageHeader eyebrow={t("nav.group.operate")} title={t("usage.title")} description={t("usage.description")} />
      <UsageControls
        days={days}
        client={sp.client ?? ""}
        source={sp.source ?? ""}
        clients={clients?.items.map((c) => ({ ref: c.external_client_ref, name: c.name })) ?? []}
        csv={csv}
      />
      {totals.length > 0 ? (
        <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-4" aria-label={t("usage.totals")}>
          {totals.map(([meter, qty]) => (
            <Metric key={meter} label={meter} value={formatNumber(qty, locale)} hint={t("usage.period", { days })} />
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
                  <td className="p-2 text-right tabular-nums">{formatNumber(b.quantity, locale)}</td>
                  <td className="p-2 text-right tabular-nums">{b.source === "qa" ? "—" : formatNumber(b.billable_qty, locale)}</td>
                  <td className="p-2 text-right tabular-nums">{formatNumber(b.records, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
