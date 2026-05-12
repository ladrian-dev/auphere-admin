import Link from "next/link";

import { PageHeader } from "@/components/brand/page-header";
import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backend } from "@/lib/backend";
import { planLabel, relativeTime, statusLabel } from "@/lib/format";

export const metadata = { title: "Tenants" };

const STATUS_TONE: Record<string, "positive" | "warning" | "muted"> = {
  active: "positive",
  paused: "warning",
  archived: "muted",
};

export default async function TenantsPage() {
  const tenants = await backend.listTenants();
  const counts = {
    total: tenants.length,
    active: tenants.filter((t) => t.status === "active").length,
    paused: tenants.filter((t) => t.status === "paused").length,
  };

  return (
    <>
      <PageHeader
        eyebrow="Tenants"
        title="Portafolio de agentes"
        description="Cada tenant es un cliente con su propio agente bespoke. Click en una fila para abrir el detalle."
        actions={<Button render={<Link href="/tenants/new" />}>Nuevo cliente</Button>}
      />

      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <span>
          <strong className="text-foreground tabular-nums">{counts.total}</strong>{" "}
          tenants
        </span>
        <span>
          <strong className="text-foreground tabular-nums">{counts.active}</strong>{" "}
          activos
        </span>
        {counts.paused > 0 ? (
          <span>
            <strong className="text-foreground tabular-nums">{counts.paused}</strong>{" "}
            pausados
          </span>
        ) : null}
      </div>

      <div className="rounded-md border border-border bg-card overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tenant</TableHead>
              <TableHead className="hidden sm:table-cell">Plan</TableHead>
              <TableHead className="hidden md:table-cell">Mercado</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="hidden md:table-cell text-right">
                Última actualización
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tenants.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-12 text-center text-muted-foreground"
                >
                  Sin tenants todavía. Crea el primero con &quot;Nuevo
                  cliente&quot; arriba a la derecha.
                </TableCell>
              </TableRow>
            ) : (
              tenants.map((tenant) => (
                <TableRow
                  key={tenant.id}
                  className="cursor-pointer transition-colors hover:bg-muted/40"
                >
                  <TableCell>
                    <Link
                      href={`/tenants/${tenant.id}`}
                      className="flex flex-col gap-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                    >
                      <span className="font-medium">{tenant.name}</span>
                      <span className="text-xs font-mono text-muted-foreground">
                        {tenant.slug}
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <Badge variant="outline">{planLabel(tenant.plan)}</Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-muted-foreground">
                    {tenant.market ?? "—"}
                    <span className="text-xs ml-1">({tenant.timezone})</span>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-2">
                      <StatusDot
                        tone={STATUS_TONE[tenant.status] ?? "muted"}
                      />
                      <span>{statusLabel(tenant.status)}</span>
                    </span>
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-right text-muted-foreground tabular-nums">
                    {relativeTime(tenant.updated_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
