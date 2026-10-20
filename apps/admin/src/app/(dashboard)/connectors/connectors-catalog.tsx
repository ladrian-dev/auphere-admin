"use client";

import { Plug } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Badge, CatalogBrowser, EmptyState } from "@nexus/ui";

import { ConnectorAuthBadge } from "@/components/brand/connector-auth-badge";
import { ConnectorLogo } from "@/components/brand/connector-logo";
import { catalogLabels, useCatalog } from "@/components/catalog/use-catalog";
import { categoryName } from "@/components/connectors/labels";
import type { Connector } from "@/lib/backend";

/** Spec 035 (R4): Auphere's connector catalog, with how many clients use each. */
export function ConnectorsCatalog({ rows }: { rows: Array<{ connector: Connector; installs: number }> }) {
  const catalog = useCatalog("/connectors");
  const labels = React.useMemo(
    () => catalogLabels({ title: "Conectores", category: categoryName, activeLabel: "En uso" }),
    [],
  );
  const items = React.useMemo(
    () =>
      [...rows]
        .sort((a, b) => b.installs - a.installs || a.connector.display_name.localeCompare(b.connector.display_name))
        .map((r) => ({
          id: r.connector.slug,
          name: r.connector.display_name,
          search: `${r.connector.vendor} ${r.connector.capabilities.join(" ")}`,
          category: r.connector.category,
          active: r.installs > 0,
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
      renderItem={({ id, row }) => (
        <Link
          key={id}
          href={`/connectors/${encodeURIComponent(row.connector.slug)}`}
          className="flex flex-col gap-3 rounded-md p-4 ring-1 ring-foreground/10 outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring"
        >
          <div className="flex items-start justify-between gap-3">
            <ConnectorLogo connector={row.connector} size="lg" />
            {row.connector.status === "beta" ? <Badge variant="outline">Beta</Badge> : null}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">{row.connector.display_name}</span>
            <span className="text-xs text-muted-foreground">
              {row.connector.vendor} · {categoryName(row.connector.category)}
            </span>
          </div>
          <div className="mt-auto flex items-center justify-between gap-2">
            <ConnectorAuthBadge kind={row.connector.auth_kind} />
            <span className="text-xs text-muted-foreground tabular-nums">
              {row.installs === 1 ? "1 cliente" : `${row.installs} clientes`}
            </span>
          </div>
        </Link>
      )}
      empty={<EmptyState icon={Plug} title="El catálogo está vacío" readonly />}
    />
  );
}
