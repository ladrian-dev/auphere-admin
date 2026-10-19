import Link from "next/link";

import { Button, Callout, EmptyState, ErrorState, PageHeader } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { TenantsTable } from "./tenants-table";

export const metadata = { title: "Clientes" };
export const dynamic = "force-dynamic";

/**
 * Spec 036: every client, with what the operator scans for first — who needs
 * something and why — then where it is and how it is doing.
 */
export default async function TenantsPage() {
  const now = new Date();
  const [tenants, partners, periodPayments, health] = await Promise.all([
    backend.listTenants().catch(() => null),
    backend.listPartners().catch(() => []),
    backend.listPeriodPayments(now.getFullYear(), now.getMonth() + 1).catch(() => []),
    backend.listTenantsHealth().catch(() => null),
  ]);
  return (
    <>
      <PageHeader
        title="Clientes"
        description="Cada cliente es un negocio con su propio agente. Los que necesitan algo salen primero."
        actions={<Button nativeButton={false} render={<Link href="/tenants/new" />}>Nuevo cliente</Button>}
      />
      {health === null && tenants !== null ? (
        <Callout tone="warning" title="No se pudo leer la salud de los clientes">
          La lista está completa, pero sin canal, agente ni actividad. Vuelve a cargar en un momento.
        </Callout>
      ) : health && health.unreadable.length > 0 ? (
        <Callout tone="warning" title={`Faltan datos de ${health.unreadable.length} cliente(s)`}>
          Sus filas salen sin canal, agente ni actividad. El resto está completo.
        </Callout>
      ) : null}
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
          health={health?.clients ?? []}
          partners={partners.map((p) => ({ id: p.id, name: p.name }))}
          paidThisMonth={periodPayments.map((p) => p.tenant_id)}
          monthName={now.toLocaleDateString("es", { month: "long" })}
        />
      )}
    </>
  );
}
