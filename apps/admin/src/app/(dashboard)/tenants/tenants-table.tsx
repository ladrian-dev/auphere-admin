"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  Badge,
  EmptyState,
  Input,
  NativeSelect,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import { TenantActionsMenu } from "@/components/tenants/tenant-actions-menu";
import type { Tenant } from "@/lib/backend";
import { planLabel, relativeTime, statusLabel } from "@/lib/format";
import { filterRows } from "@/lib/list-filter";

const STATUS_TONE: Record<string, "positive" | "warning" | "muted"> = {
  active: "positive",
  paused: "warning",
  archived: "muted",
};

/** The partner facet's value for a client that belongs to no partner. */
export const DIRECT = "__direct__";

type Props = {
  tenants: Tenant[];
  partners: { id: string; name: string }[];
  paidThisMonth: string[];
  monthName: string;
};

/** Spec 031 (R5.1, R5.2): every client, the partner it belongs to, and filters. */
export function TenantsTable({ tenants, partners, paidThisMonth, monthName }: Props) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [partner, setPartner] = useState("");
  const [plan, setPlan] = useState("");
  const paid = useMemo(() => new Set(paidThisMonth), [paidThisMonth]);
  const partnerName = useMemo(() => new Map(partners.map((p) => [p.id, p.name])), [partners]);

  const rows = useMemo(
    () =>
      filterRows(
        tenants,
        q,
        (t) => [t.name, t.slug, t.owner_email, t.partner_id ? partnerName.get(t.partner_id) : "Auphere directo"],
        [
          { value: status, of: (t) => t.status },
          { value: partner, of: (t) => t.partner_id ?? DIRECT },
          { value: plan, of: (t) => t.plan },
        ],
      ),
    [tenants, q, status, partner, plan, partnerName],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por nombre, slug o correo"
          aria-label="Buscar clientes"
          className="lg:max-w-xs"
        />
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtrar por estado" wrapperClassName="lg:w-44">
          <option value="">Todos los estados</option>
          <option value="active">Activos</option>
          <option value="paused">En pausa</option>
          <option value="archived">Archivados</option>
        </NativeSelect>
        <NativeSelect value={partner} onChange={(e) => setPartner(e.target.value)} aria-label="Filtrar por partner" wrapperClassName="lg:w-52">
          <option value="">Todos los partners</option>
          <option value={DIRECT}>Auphere directo</option>
          {partners.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect value={plan} onChange={(e) => setPlan(e.target.value)} aria-label="Filtrar por plan" wrapperClassName="lg:w-40">
          <option value="">Todos los planes</option>
          {(["essential", "pro", "business", "internal"] as const).map((p) => (
            <option key={p} value={p}>
              {planLabel(p)}
            </option>
          ))}
        </NativeSelect>
        <p className="text-sm text-muted-foreground lg:ml-auto" aria-live="polite">
          {rows.length === tenants.length ? `${tenants.length} clientes` : `${rows.length} de ${tenants.length}`}
        </p>
      </div>
      {rows.length === 0 ? (
        <EmptyState title="Ningún cliente coincide" description="Prueba con otro nombre o quita algún filtro." readonly />
      ) : (
        <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cliente</TableHead>
                <TableHead>Partner</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="hidden sm:table-cell">Plan</TableHead>
                <TableHead className="hidden md:table-cell">Mensualidad de {monthName}</TableHead>
                <TableHead className="hidden lg:table-cell text-right">Actualizado</TableHead>
                <TableHead className="w-12" aria-label="Acciones" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <Link href={`/tenants/${t.id}`} className="flex flex-col gap-1 rounded-sm outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring">
                      <span className="font-medium">{t.name || "Sin nombre"}</span>
                      <span className="font-mono text-xs text-muted-foreground">{t.slug}</span>
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm">
                    {t.partner_id ? (
                      <Link href={`/partners/${t.partner_id}`} className="underline-offset-4 hover:underline">
                        {partnerName.get(t.partner_id) ?? "Partner"}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">Auphere directo</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot tone={STATUS_TONE[t.status] ?? "muted"} />
                      {statusLabel(t.status)}
                    </span>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <Badge variant="outline">{planLabel(t.plan)}</Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {paid.has(t.id) ? (
                      <Badge variant="secondary">Pagada</Badge>
                    ) : t.billing_plan_id ? (
                      <Link href={`/tenants/${t.id}/billing`} className="text-sm text-muted-foreground underline-offset-4 hover:underline">
                        Sin anotar
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-right text-sm text-muted-foreground tabular-nums">
                    {relativeTime(t.updated_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <TenantActionsMenu tenantId={t.id} slug={t.slug} name={t.name} status={t.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
