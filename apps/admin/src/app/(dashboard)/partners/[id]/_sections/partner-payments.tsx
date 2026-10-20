import { Card, CardContent, CardDescription, CardHeader, CardTitle, Eyebrow } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { PartnerPaymentsClient } from "./partner-payments-client";

/**
 * The partner's payments outside Stripe (owner, 2026-10-20). The partner pays
 * Auphere, not its client: a payment is recorded for one of its clients and a
 * month, and it credits the partner's balance once. Voiding takes it back.
 */
export default async function PartnerPayments({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [payments, tenants] = await Promise.all([
    backend.listPartnerPayments(id).catch(() => null),
    backend.listPartnerTenants(id).catch(() => []),
  ]);
  // What each client pays a month, to fill the amount when it is picked.
  const billing = await Promise.all(
    tenants.map((t) => backend.getTenantBilling(t.tenant_id).catch(() => null)),
  );
  const clients = tenants.map((t, i) => ({
    tenantId: t.tenant_id,
    name: billing[i]?.tenant_name ?? t.client_name ?? t.external_client_ref,
    monthlyCents: billing[i]?.effective_monthly_cents ?? null,
  }));

  return (
    <Card>
      <CardHeader>
        <Eyebrow>Pagos</Eyebrow>
        <CardTitle>Pagos recibidos fuera de Stripe</CardTitle>
        <CardDescription>
          Lo que el partner pagó por transferencia, cripto u otro medio, por cada cliente y mes. Anotar un pago suma
          su importe al saldo recargado del partner; anularlo lo descuenta.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {payments === null ? (
          <p role="status" className="text-sm text-status-warning-text">
            No se pudieron leer los pagos. Prueba a recargar.
          </p>
        ) : (
          <PartnerPaymentsClient partnerId={id} payments={payments} clients={clients} />
        )}
      </CardContent>
    </Card>
  );
}
