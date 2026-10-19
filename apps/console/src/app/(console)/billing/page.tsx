import { redirect } from "next/navigation";

import { Button, DescriptionList, EmptyState, PageHeader, StatusBadge, formatCurrency, formatDate } from "@nexus/ui";

import { BuyCreditForm } from "@/components/billing/buy-credit-form";
import { CardSection } from "@/components/billing/card-section";
import { MembershipSection } from "@/components/billing/membership-section";
import { ProviderInvoicesLink } from "@/components/billing/provider-invoices-link";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.billing");

export default async function BillingPage({ searchParams }: { searchParams: Promise<{ card?: string }> }) {
  const principal = await requirePartnerPrincipal("/billing");
  if (!can(principal.role, "billing:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  const backend = backendFor(principal);
  const billing = await backend.billing();
  // Spec 034: the plans belong to the Teammate and are off while it is being
  // finished. Off, the screen has no plans and no provider portal: the
  // balance purchase and the receipts are all there is (§V — absence is
  // designed, not greyed out).
  const membership = billing.memberships_enabled ? await backend.membership() : null;
  // Spec 041: the card and automatic charging. A read that fails hides the
  // section rather than drawing a card that may not be the real one.
  const card = membership ? null : await backend.billingCard().catch(() => null);
  const justSaved = (await searchParams).card === "saved";
  return (
    <>
      <PageHeader
        eyebrow={t("nav.group.account")}
        title={t("billing.title")}
        description={t(membership ? "billing.description" : "billing.descriptionFree")}
      />
      {membership ? (
        <MembershipSection membership={membership} />
      ) : can(principal.role, "billing:manage") ? (
        <section aria-labelledby="credit-h" className="flex max-w-lg flex-col gap-3">
          <h2 id="credit-h" className="text-lg font-semibold">
            {t("membership.credit.title")}
          </h2>
          <p className="text-sm text-pretty text-muted-foreground">{t("membership.credit.help")}</p>
          <BuyCreditForm />
        </section>
      ) : null}
      {card ? <CardSection view={card} canManage={can(principal.role, "billing:manage")} justSaved={justSaved} /> : null}
      <DescriptionList layout="inline" className="max-w-lg" items={[{ key: "email", term: t("billing.email"), detail: billing.billing_email ?? t("billing.notSet"), mono: true, truncate: true }]} />
      <section aria-labelledby="receipts-h" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="receipts-h" className="text-lg font-semibold">
            {t("billing.receipts")}
          </h2>
          {/* Spec 005 R8.4: la factura del proveedor es el documento fiscal;
              este recibo explica el consumo. Los dos papeles, y el camino al
              otro documento donde se busca. */}
          <ProviderInvoicesLink hasSubscription={membership !== null && membership.tier.code !== "free"} />
        </div>
        {membership ? (
          <p className="text-muted-foreground text-sm text-pretty">
            {t("membership.invoices.help")}
          </p>
        ) : null}
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
                  <th className="h-10 px-2 text-right font-medium">
                    <span className="sr-only">{t("common.actions")}</span>
                  </th>
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
                    <td className="p-2 text-right">
                      <Button nativeButton={false} variant="outline" size="xs" render={<a href={`/api/billing/receipts/${r.invoice_id}`} download title={t("hu.billing.download.title")} />}>
                        {t("hu.billing.download")}
                      </Button>
                    </td>
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
