import Link from "next/link";

import { Eyebrow } from "@/components/brand/eyebrow";
import { AuditRow } from "@/components/audit/audit-row";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";

import { AuditFilters } from "./filters";

type SearchParams = {
  cursor?: string;
  actor?: string;
  action?: string;
  target?: string;
  after?: string;
  before?: string;
};

/**
 * Per-tenant audit timeline (Bloque B4).
 *
 * Reads ``audit_log`` newest-first. Filters live in the URL search
 * params so the operator can deep-link and bookmark useful slices
 * ("show me every connector connect/disconnect this week"). Pagination
 * is cursor-based — clicking "Cargar más" advances by ``next_cursor``.
 *
 * Diff rendering happens per-row in ``AuditRow`` — click any row with
 * before/after json to expand the two-column diff panel.
 */
export default async function AuditPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { id } = await params;
  const filters = await searchParams;
  const [tenant, page, actions] = await Promise.all([
    backend.getTenant(id),
    backend.listAuditLog(id, {
      cursor: filters.cursor,
      actor: filters.actor,
      action: filters.action,
      target: filters.target,
      after: filters.after,
      before: filters.before,
      limit: 50,
    }),
    backend.listAuditActions(id),
  ]);
  if (!tenant) return null;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow>Auditoría</Eyebrow>
          <CardTitle>Historial de cambios</CardTitle>
          <CardDescription>
            Toda promoción, toggle de capacidad, conexión de connector,
            escalación de conversación y mutación del tenant queda registrada.
            Tocá una fila con diff para ver el antes/después.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <AuditFilters
            tenantId={tenant.id}
            actions={actions}
            current={{
              actor: filters.actor ?? "",
              action: filters.action ?? "",
              target: filters.target ?? "",
              after: filters.after ?? "",
              before: filters.before ?? "",
            }}
          />
          {page.items.length === 0 ? (
            <div className="rounded-md border border-dashed py-12 text-center text-sm text-muted-foreground">
              Sin entradas que matcheen estos filtros.
            </div>
          ) : (
            <div className="grid gap-2">
              {page.items.map((entry) => (
                <AuditRow key={entry.id} entry={entry} />
              ))}
            </div>
          )}
          {page.next_cursor ? (
            <NextPageLink
              tenantId={tenant.id}
              cursor={page.next_cursor}
              filters={filters}
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function NextPageLink({
  tenantId,
  cursor,
  filters,
}: {
  tenantId: string;
  cursor: string;
  filters: SearchParams;
}) {
  const qs = new URLSearchParams();
  for (const k of ["actor", "action", "target", "after", "before"] as const) {
    const v = filters[k];
    if (v) qs.set(k, v);
  }
  qs.set("cursor", cursor);
  return (
    <div className="flex justify-center">
      <Link
        href={`/tenants/${tenantId}/audit?${qs.toString()}`}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-muted"
      >
        Cargar más →
      </Link>
    </div>
  );
}
