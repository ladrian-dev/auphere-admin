import { redirect } from "next/navigation";

import { Button, Card, CardContent, EmptyState, PageHeader, StatusBadge, formatCurrency, formatDate } from "@nexus/ui";

import { BillingEmailForm } from "@/components/billing/billing-email-form";
import { BuyCreditForm } from "@/components/billing/buy-credit-form";
import { CardCharges, CardSection } from "@/components/billing/card-section";
import { MembershipSection } from "@/components/billing/membership-section";
import { ProviderInvoicesLink } from "@/components/billing/provider-invoices-link";
import { receiptStatus } from "@/components/billing/receipt-status";
import { moneyText } from "@/components/money/money-model";
import { resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor, callFor } from "@/lib/backend";
import { moneyApi } from "@/lib/backend/money";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.billing");

export default async function BillingPage({ searchParams }: { searchParams: Promise<{ card?: string; invoice?: string; recargar?: string }> }) {
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
  const params = await searchParams;
  // Spec 047 (49.3): con la consola nueva, Facturación dice la moneda de la
  // cuenta y lo que se puede asignar, en esa moneda (la misma cifra que Consumo).
  const v2 = resolveConsoleVersion(await backend.me().catch(() => null)) === "v2";
  const account = v2 && can(principal.role, "usage:read") ? await moneyApi(callFor(principal)).usageSummary().catch(() => null) : null;
  const justSaved = params.card === "saved";
  const canManage = can(principal.role, "billing:manage");
  const showWallet = Boolean(account) || (!membership && canManage);
  const invoiceMissing = params.invoice === "missing";
  return (
    <>
      <PageHeader
        size="display"
        title={t("billing.title")}
        description={t(membership ? "billing.description" : "billing.descriptionFree")}
      />
      {membership ? <MembershipSection membership={membership} /> : null}
      {/* Spec 047 (prototipo): «Saldo de tu cuenta» y «Tarjeta y cobro
          automático» lado a lado; en pantallas estrechas, una debajo de otra. */}
      {showWallet || card ? (
        <div className={showWallet && card ? "grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]" : "grid min-w-0 gap-4"} data-slot="billing-panel">
          {showWallet ? (
            <Card aria-labelledby="wallet-h" role="region" data-slot="billing-wallet">
              <CardContent className="grid min-w-0 gap-4">
                <h2 id="wallet-h" className="text-base font-semibold">
                  {t("proto.billing.wallet")}
                </h2>
                {account ? (
                  <div className="flex min-w-0 flex-wrap items-end justify-between gap-x-6 gap-y-2">
                    <div className="grid gap-1">
                      <p className="text-xs text-muted-foreground">{t("proto.billing.available")}</p>
                      <p className="text-2xl font-semibold tracking-tight tabular-nums">{moneyText(account.available, "down")}</p>
                    </div>
                    <div className="grid text-sm text-pretty text-muted-foreground sm:text-right">
                      <p>{t("proto.billing.spentBy")}</p>
                      <p>{t("proto.billing.keeps")}</p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-pretty text-muted-foreground">{t("membership.credit.help")}</p>
                )}
                {!membership && canManage ? (
                  <BuyCreditForm initialAmount={params.recargar ?? null} accountCurrency={account?.currency ?? null} label={t("membership.credit.title")} />
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          {card ? <CardSection view={card} canManage={canManage} justSaved={justSaved} invoiceMissing={invoiceMissing} /> : null}
        </div>
      ) : null}
      <BillingEmailForm email={billing.billing_email} contactEmail={billing.contact_email ?? null} canManage={canManage} />
      {card ? <CardCharges view={card} canManage={canManage} /> : null}
      <Card aria-labelledby="receipts-h" role="region" data-slot="billing-receipts">
        <CardContent className="grid min-w-0 gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="receipts-h" className="text-base font-semibold">
              {t("billing.receipts")}
            </h2>
            {/* Spec 005 R8.4: la factura del proveedor es el documento fiscal;
                este recibo explica el consumo. Los dos papeles, y el camino al
                otro documento donde se busca. */}
            <ProviderInvoicesLink hasSubscription={membership !== null && membership.tier.code !== "free"} />
          </div>
          {membership ? <p className="text-sm text-pretty text-muted-foreground">{t("membership.invoices.help")}</p> : null}
          {billing.receipts.length === 0 ? (
            <EmptyState title={t("billing.receipts.empty")} readonly />
          ) : (
            <div className="min-w-0 overflow-x-auto rounded-lg ring-1 ring-foreground/10">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="h-12 px-4 font-normal">{t("billing.period")}</th>
                    <th className="h-12 px-4 font-normal">{t("common.status")}</th>
                    <th className="h-12 px-4 text-right font-normal">{t("billing.total")}</th>
                    <th className="h-12 px-4 font-normal">{t("billing.due")}</th>
                    <th className="h-12 px-4 text-right font-normal">
                      <span className="sr-only">{t("common.actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {billing.receipts.map((r) => {
                    const state = receiptStatus(r.status, t);
                    return (
                      <tr key={r.invoice_id} className="border-b last:border-0">
                        <td className="px-4 py-3 tabular-nums">
                          {r.period_year}-{String(r.period_month).padStart(2, "0")}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(r.total_usd, r.currency, locale)}</td>
                        <td className="px-4 py-3 tabular-nums">{formatDate(r.due_date, locale)}</td>
                        <td className="px-4 py-3 text-right">
                          <Button nativeButton={false} variant="ghost" size="sm" render={<a href={`/api/billing/receipts/${r.invoice_id}`} download title={t("hu.billing.download.title")} />}>
                            {t("hu.billing.download")}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
