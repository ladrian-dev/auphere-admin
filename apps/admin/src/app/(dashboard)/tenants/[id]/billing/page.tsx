import { notFound } from "next/navigation";

import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Eyebrow } from "@nexus/ui";
import { backend } from "@/lib/backend";

import { BillingForm } from "./billing-form";
import { PaymentsCard } from "./payments-card";

const MODEL_LABEL: Record<string, string> = {
  subscription: "Suscripción",
  commission: "Comisión",
  inactive: "Inactivo",
};

function usd(cents: number | null): string {
  return cents == null
    ? "—"
    : (cents / 100).toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
      });
}

/**
 * Facturación del tenant. Muestra cómo se factura este tenant (partner,
 * plan, precio, inicio) y permite editarlo. Un tenant sin partner es un
 * cliente directo de Auphere (Auphere no es un partner). El "plan" aquí es
 * la suscripción en USD, distinta del tier del producto.
 */
export default async function TenantBillingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [billing, partners, plans, payments] = await Promise.all([
    backend.getTenantBilling(id),
    backend.listPartners(),
    backend.listBillingPlans(),
    backend.listTenantPayments(id),
  ]);
  if (!billing) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Facturación</Eyebrow>
          <CardTitle>Cómo se factura {billing.tenant_name}</CardTitle>
          <CardDescription>
            El cobro de este tenant se consolida en el recibo mensual de su
            partner. Sin partner, es cliente directo de Auphere.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1">
              <dt className="text-xs text-muted-foreground">Modelo</dt>
              <dd>
                <Badge variant="secondary">
                  {MODEL_LABEL[billing.model] ?? billing.model}
                </Badge>
              </dd>
            </div>
            <div className="grid gap-1">
              <dt className="text-xs text-muted-foreground">Partner</dt>
              <dd className="text-sm">
                {billing.partner_name ?? (
                  <span className="text-muted-foreground">
                    Auphere (directo)
                  </span>
                )}
              </dd>
            </div>
            <div className="grid gap-1">
              <dt className="text-xs text-muted-foreground">Plan</dt>
              <dd className="text-sm">
                {billing.plan_name ? (
                  <>
                    {billing.plan_name} · {usd(billing.plan_amount_cents)}/mes
                  </>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </dd>
            </div>
            <div className="grid gap-1">
              <dt className="text-xs text-muted-foreground">
                Cobro mensual efectivo
              </dt>
              <dd className="text-sm tabular-nums">
                {billing.model === "commission"
                  ? "2,5% de ventas (variable)"
                  : usd(billing.effective_monthly_cents)}
              </dd>
            </div>
            {billing.billing_effective_from && (
              <div className="grid gap-1">
                <dt className="text-xs text-muted-foreground">
                  Inicio de facturación
                </dt>
                <dd className="text-sm tabular-nums">
                  {billing.billing_effective_from}
                </dd>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Pagos</Eyebrow>
          <CardTitle>Pagos recibidos fuera de Stripe</CardTitle>
          <CardDescription>
            {billing.partner_id
              ? "Lo que su partner pagó por este cliente fuera de Stripe. Se anota en las Facturas del partner y suma a su saldo."
              : "Mensualidades que este cliente directo pagó por transferencia, efectivo u otro medio. Anotar un pago deja constancia de quién pagó qué mes."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PaymentsCard
            tenantId={id}
            payments={payments}
            monthlyCents={billing.effective_monthly_cents}
            partner={billing.partner_id ? { id: billing.partner_id, name: billing.partner_name } : null}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Editar</Eyebrow>
          <CardTitle>Configuración de facturación</CardTitle>
          <CardDescription>
            Asigna el partner, el plan de suscripción (USD/mes), un precio
            negociado y la fecha de inicio. Los cambios impactan el próximo
            recibo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BillingForm
            tenantId={id}
            billing={billing}
            partners={partners}
            plans={plans}
          />
        </CardContent>
      </Card>
    </div>
  );
}
