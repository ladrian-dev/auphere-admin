import { redirect } from "next/navigation";

import { EmptyState, PageHeader, StatusBadge, formatCurrency, formatDate } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Facturación" };

export default async function BillingPage() {
  const principal = await requirePrincipal("/billing");
  if (!can(principal.role, "billing:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const billing = await backendFor(principal).billing();
  return (
    <>
      <PageHeader eyebrow={t("nav.group.account")} title={t("billing.title")} description={t("billing.description")} />
      <dl className="grid max-w-lg grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">{t("billing.email")}</dt>
        <dd className="min-w-0 truncate font-mono">{billing.billing_email ?? t("billing.notSet")}</dd>
      </dl>
      <section aria-labelledby="receipts-h" className="flex flex-col gap-3">
        <h2 id="receipts-h" className="text-lg font-semibold">
          {t("billing.receipts")}
        </h2>
        {billing.receipts.length === 0 ? (
          <EmptyState title={t("billing.receipts.empty")} readonly />
        ) : (
          <div className="min-w-0 overflow-x-auto rounded-md ring-1 ring-foreground/10">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="h-10 px-2 font-medium">{t("billing.period")}</th>
                  <th className="h-10 px-2 font-medium">{t("common.status")}</th>
                  <th className="h-10 px-2 text-right font-medium">{t("billing.total")}</th>
                  <th className="h-10 px-2 font-medium">{t("billing.due")}</th>
                </tr>
              </thead>
              <tbody>
                {billing.receipts.map((r) => (
                  <tr key={r.invoice_id} className="border-b last:border-0">
                    <td className="p-2 font-mono tabular-nums">
                      {r.period_year}-{String(r.period_month).padStart(2, "0")}
                    </td>
                    <td className="p-2">
                      <StatusBadge tone={r.status === "paid" ? "positive" : r.status === "issued" ? "info" : "muted"}>{r.status}</StatusBadge>
                    </td>
                    <td className="p-2 text-right tabular-nums">{formatCurrency(r.total_usd, r.currency, locale)}</td>
                    <td className="p-2 tabular-nums">{formatDate(r.due_date, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
