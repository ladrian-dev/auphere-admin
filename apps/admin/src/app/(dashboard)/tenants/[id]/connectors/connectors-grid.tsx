"use client";

import { Plug, Settings2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, CatalogBrowser, EmptyState, StatusDot } from "@nexus/ui";

import { ConnectorLogo } from "@/components/brand/connector-logo";
import { catalogLabels, useCatalog } from "@/components/catalog/use-catalog";
import { categoryName, connectorState, urgency } from "@/components/connectors/labels";
import type { Connector, TenantConnectorStatus } from "@/lib/backend";

export type GridConnector = { connector: Connector; status: TenantConnectorStatus | null };

/**
 * Spec 035: the client's connectors, like Chatwoot's Integrations — a card
 * per app with its logo, state and «Configurar», searchable and grouped by
 * the partner console's categories. What broke goes first.
 */
export function ConnectorsGrid({ tenantId, rows }: { tenantId: string; rows: GridConnector[] }) {
  const base = `/tenants/${tenantId}/connectors`;
  const catalog = useCatalog(base);
  const labels = React.useMemo(
    () => catalogLabels({ title: "Conectores", category: categoryName, activeLabel: "Activados" }),
    [],
  );
  const items = React.useMemo(
    () =>
      [...rows]
        .sort(
          (a, b) =>
            urgency(a.status) - urgency(b.status) ||
            a.connector.display_name.localeCompare(b.connector.display_name),
        )
        .map((r) => ({
          id: r.connector.slug,
          name: r.connector.display_name,
          search: `${r.connector.vendor} ${r.connector.capabilities.join(" ")}`,
          category: r.connector.category,
          active: connectorState(r.status).active,
          row: r,
        })),
    [rows],
  );

  return (
    <CatalogBrowser
      {...catalog}
      items={items}
      labels={labels}
      renderLink={(href, children, props) => (
        <Link href={href} {...props}>
          {children}
        </Link>
      )}
      renderItem={({ id, row }) => {
        const state = connectorState(row.status);
        return (
          <div key={id} className="flex flex-col gap-4 rounded-md p-4 ring-1 ring-foreground/10">
            <div className="flex items-start justify-between gap-3">
              <ConnectorLogo connector={row.connector} />
              <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <StatusDot tone={state.tone} />
                {state.label}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-sm font-medium">{row.connector.display_name}</span>
              <span className="text-xs text-muted-foreground">
                {row.connector.vendor} · {categoryName(row.connector.category)}
              </span>
            </div>
            <div className="mt-auto">
              <Button
                nativeButton={false}
                variant="outline"
                size="sm"
                render={<Link href={`${base}/${encodeURIComponent(row.connector.slug)}`} />}
              >
                <Settings2 aria-hidden="true" />
                Configurar
              </Button>
            </div>
          </div>
        );
      }}
      empty={
        <EmptyState
          icon={Plug}
          title="No hay conectores en el catálogo"
          description="Cuando Auphere publique uno, aparecerá aquí."
          readonly
        />
      }
    />
  );
}
