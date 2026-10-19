import Link from "next/link";

import { Button, EmptyState, ErrorState, PageHeader } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { TenantsTable } from "./tenants-table";

export const metadata = { title: "Clientes" };
export const dynamic = "force-dynamic";

/**
 * Spec 031 (R5.1): every business with its own agent, and whose it is — a
 * partner's client or a direct Auphere client.
 */
export default async function TenantsPage() {
  const now = new Date();
  const [tenants, partners, periodPayments] = await Promise.all([
    backend.listTenants().catch(() => null),
    backend.listPartners().catch(() => []),
    backend.listPeriodPayments(now.getFullYear(), now.getMonth() + 1).catch(() => []),
  ]);
  return (
    <>
      <PageHeader
        title="Clientes"
        description="Cada cliente es un negocio con su propio agente. Los de un partner los opera el partner desde su consola."
        actions={<Button nativeButton={false} render={<Link href="/tenants/new" />}>Nuevo cliente</Button>}
      />
      {tenants === null ? (
        <ErrorState title="No se pudieron leer los clientes" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : tenants.length === 0 ? (
        <EmptyState
          title="Todavía no hay clientes"
          description="Crea el primero para darle su agente."
          action={<Button nativeButton={false} render={<Link href="/tenants/new" />}>Nuevo cliente</Button>}
        />
      ) : (
        <TenantsTable
          tenants={tenants}
          partners={partners.map((p) => ({ id: p.id, name: p.name }))}
          paidThisMonth={periodPayments.map((p) => p.tenant_id)}
          monthName={now.toLocaleDateString("es", { month: "long" })}
        />
      )}
    </>
  );
}
