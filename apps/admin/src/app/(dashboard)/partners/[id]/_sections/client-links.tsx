import Link from "next/link";
import { notFound } from "next/navigation";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Eyebrow,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import { backend } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import { LinkTenantForm } from "./link-tenant-form";

/**
 * Mapeos partner → tenant. Cada cliente final del partner (identificado
 * por su ``external_client_ref``) apunta a un tenant Nexus. El partner
 * nunca ve el tenant_id — solo su propio ref; este panel sí, porque el
 * operador necesita cruzar ambos mundos.
 */
export default async function PartnerTenantsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [partner, mappings] = await Promise.all([
    backend.getPartner(id),
    backend.listPartnerTenants(id),
  ]);
  if (!partner) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Clientes</Eyebrow>
          <CardTitle>Clientes mapeados</CardTitle>
          <CardDescription>
            Relación entre el <code>external_client_ref</code> del partner y
            el tenant Nexus que atiende a ese cliente. El partner solo conoce
            su ref; el tenant_id es interno.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {mappings.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Sin clientes mapeados todavía. Agrega el primero con el
              formulario de abajo, o espera a que el partner provisione vía{" "}
              <code>/v1/partners/clients</code>.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ref del partner</TableHead>
                    <TableHead className="hidden sm:table-cell">
                      Cliente
                    </TableHead>
                    <TableHead>Ficha</TableHead>
                    <TableHead className="hidden md:table-cell text-right">
                      Mapeado
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mappings.map((m) => (
                    <TableRow key={`${m.partner_id}-${m.external_client_ref}`}>
                      <TableCell className="font-mono text-xs">
                        {m.external_client_ref}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        {m.client_name ?? (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Link
                          href={`/tenants/${m.tenant_id}`}
                          className="font-mono text-xs text-primary-text underline-offset-4 hover:underline"
                          title={m.tenant_id}
                        >
                          Abrir ficha →
                        </Link>
                      </TableCell>
                      <TableCell className="hidden md:table-cell text-right text-muted-foreground tabular-nums">
                        {relativeTime(m.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Alta manual</Eyebrow>
          <CardTitle>Mapear cliente a tenant</CardTitle>
          <CardDescription>
            Para migraciones o correcciones. Un mismo ref no puede apuntar a
            dos tenants — el backend responde 409 si ya está mapeado.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LinkTenantForm partnerId={partner.id} />
        </CardContent>
      </Card>
    </div>
  );
}
