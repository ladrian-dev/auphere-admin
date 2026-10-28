import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import {
  Badge,
  DescriptionList,
  EmptyState,
  PageHeader,
  Section,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import { ConnectorAuthBadge } from "@/components/brand/connector-auth-badge";
import { ConnectorLogo } from "@/components/brand/connector-logo";
import { AUTH_KIND_HINT, categoryName, connectorState, isChannelOnly } from "@/components/connectors/labels";
import { SettingsFields } from "@/components/connectors/settings-fields";
import { CrumbName } from "@/components/shell/crumb-names";
import { backend, type TenantConnectorStatus } from "@/lib/backend";

export const metadata = { title: "Conector" };
export const dynamic = "force-dynamic";

/** Spec 035 (R4): one connector of the catalog and the clients that use it. */
export default async function ConnectorPage({ params }: { params: Promise<{ slug: string }> }) {
  const slug = decodeURIComponent((await params).slug);
  const [connector, installs] = await Promise.all([
    backend.getConnector(slug),
    backend.listConnectorInstalls().catch(() => ({}) as Record<string, never>),
  ]);
  if (!connector) notFound();
  if (isChannelOnly(connector)) redirect("/channels");
  const clients = [...(installs[slug] ?? [])].sort((a, b) => a.tenant_name.localeCompare(b.tenant_name));

  return (
    <>
      <CrumbName id={slug} label={connector.display_name} />
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            <ConnectorLogo connector={connector} size="xl" />
            {connector.display_name}
          </span>
        }
        description={AUTH_KIND_HINT[connector.auth_kind]}
      />
      <DescriptionList
        columns={3}
        items={[
          { term: "Proveedor", detail: connector.vendor },
          { term: "Categoría", detail: categoryName(connector.category) },
          { term: "Acceso", detail: <ConnectorAuthBadge kind={connector.auth_kind} /> },
          { term: "Estado en el catálogo", detail: connector.status === "beta" ? "Beta" : "Disponible" },
          {
            term: "Al conectar",
            detail: connector.auto_enable_destructive
              ? "Las herramientas que cambian datos quedan activas."
              : "Las herramientas que cambian datos esperan aprobación.",
          },
          {
            term: "Capacidades",
            detail:
              connector.capabilities.length > 0 ? (
                <span className="flex flex-wrap gap-1">
                  {connector.capabilities.map((c) => (
                    <Badge key={c} variant="outline">
                      {c}
                    </Badge>
                  ))}
                </span>
              ) : (
                "—"
              ),
          },
        ]}
      />
      <Section
        flat
        title="Ajustes que pide"
        description="Lo que cada agente rellena al activarlo, en la página del conector. La API lo valida con este esquema."
      >
        <SettingsFields schema={connector.settings_schema} />
      </Section>
      <Section flat title="Clientes que lo usan">
        {clients.length === 0 ? (
          <EmptyState
            title="Ningún cliente lo ha conectado"
            description="Se conecta desde la ficha del cliente, en Conectores."
            readonly
          />
        ) : (
          <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Ficha</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clients.map((c) => {
                  const st = connectorState(c.status as TenantConnectorStatus);
                  return (
                    <TableRow key={c.tenant_id}>
                      <TableCell>
                        <Link href={`/tenants/${c.tenant_id}`} className="hover:underline">
                          {c.tenant_name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-2">
                          <StatusDot tone={st.tone} />
                          {st.label}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Link
                          href={`/tenants/${c.tenant_id}/connectors/${encodeURIComponent(slug)}`}
                          className="text-sm text-primary-deep hover:underline"
                        >
                          Configurar
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
    </>
  );
}
