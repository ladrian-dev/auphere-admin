"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
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

import type { PartnerOut } from "@/lib/backend";
import { formatCents, relativeTime, statusLabel } from "@/lib/format";
import { filterRows } from "@/lib/list-filter";

const STATUS_TONE: Record<string, "positive" | "danger" | "muted"> = { active: "positive", suspended: "danger" };

/** Spec 031 (R4.1, R4.2): every partner with what the operator checks first. */
export function PartnersTable({ partners }: { partners: PartnerOut[] }) {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const rows = useMemo(
    () =>
      filterRows(partners, q, (p) => [p.name, p.slug, p.contact_email, p.billing_email], [
        { value: status, of: (p) => p.status },
      ]),
    [partners, q, status],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por nombre, slug o correo"
          aria-label="Buscar partners"
          className="sm:max-w-xs"
        />
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filtrar por estado" wrapperClassName="sm:w-48">
          <option value="">Todos los estados</option>
          <option value="active">Activos</option>
          <option value="suspended">Suspendidos</option>
        </NativeSelect>
        <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
          {rows.length === partners.length ? `${partners.length} partners` : `${rows.length} de ${partners.length}`}
        </p>
      </div>
      {rows.length === 0 ? (
        <EmptyState title="Ningún partner coincide" description="Prueba con otro nombre o quita el filtro de estado." readonly />
      ) : (
        <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Partner</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="hidden md:table-cell">Consola</TableHead>
                <TableHead className="text-right">Clientes</TableHead>
                <TableHead className="hidden sm:table-cell text-right">Personas</TableHead>
                <TableHead className="text-right">Saldo</TableHead>
                <TableHead className="hidden lg:table-cell">Contacto</TableHead>
                <TableHead className="hidden lg:table-cell text-right">Alta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id} className="relative">
                  <TableCell>
                    <Link href={`/partners/${p.id}`} className="font-medium after:absolute after:inset-0 hover:underline">
                      {p.name}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{p.slug}</div>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot tone={STATUS_TONE[p.status] ?? "muted"} />
                      {statusLabel(p.status)}
                    </span>
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                    {p.console_enabled ? "Encendida" : "Apagada"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{p.clients_count ?? "—"}</TableCell>
                  <TableCell className="hidden sm:table-cell text-right tabular-nums">{p.members_count ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatCents(p.available_cents)}</TableCell>
                  <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">{p.contact_email ?? "—"}</TableCell>
                  <TableCell className="hidden lg:table-cell text-right text-sm text-muted-foreground">{relativeTime(p.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
