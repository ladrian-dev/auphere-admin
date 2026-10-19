"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  EmptyState,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@nexus/ui";

import type { UsageOverview } from "@/lib/backend";
import { formatCents } from "@/lib/format";
import { filterRows } from "@/lib/list-filter";

import { formatUsd } from "./period";

type View = "partners" | "clients";

/**
 * Spec 038: the same money by partner and by client. The highest spend comes
 * first (serial position); each row opens its partner or client.
 */
export function UsageTables({ data }: { data: UsageOverview }) {
  const [view, setView] = useState<View>("partners");
  const [q, setQ] = useState("");
  const clients = useMemo(
    () => filterRows(data.clients, q, (c) => [c.name, c.partner_name ?? "Auphere directo"]),
    [data.clients, q],
  );
  const partners = useMemo(() => filterRows(data.partners, q, (p) => [p.name]), [data.partners, q]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <nav aria-label="Ver el consumo por" className="flex gap-1 border-b border-border">
          {(
            [
              ["partners", `Por partner (${data.partners.length})`],
              ["clients", `Por cliente (${data.clients.length})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={view === key}
              onClick={() => setView(key)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                view === key ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </nav>
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={view === "partners" ? "Buscar partner" : "Buscar cliente o partner"}
          aria-label="Buscar"
          className="md:max-w-xs"
        />
      </div>

      {view === "partners" ? (
        partners.length === 0 ? (
          <EmptyState title="Ningún partner coincide" readonly />
        ) : (
          <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Partner</TableHead>
                  <TableHead className="text-right">Gasto</TableHead>
                  <TableHead className="hidden text-right md:table-cell">Fuera de clientes</TableHead>
                  <TableHead className="hidden text-right lg:table-cell">Coste interno</TableHead>
                  <TableHead className="hidden text-right sm:table-cell">Mensajes</TableHead>
                  <TableHead className="text-right">Saldo disponible</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {partners.map((p) => (
                  <TableRow key={p.partner_id} className="relative hover:bg-muted/50">
                    <TableCell>
                      <Link
                        href={`/partners/${p.partner_id}/clients`}
                        className="flex flex-col gap-1 outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
                      >
                        <span className="font-medium">{p.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {p.clients} {p.clients === 1 ? "cliente" : "clientes"}
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{formatCents(p.spend_cents)}</TableCell>
                    <TableCell className="hidden text-right text-muted-foreground tabular-nums md:table-cell">
                      {formatCents(p.spend_outside_clients_cents)}
                    </TableCell>
                    <TableCell className="hidden text-right text-muted-foreground tabular-nums lg:table-cell">
                      {formatUsd(p.internal_cost_usd)}
                    </TableCell>
                    <TableCell className="hidden text-right tabular-nums sm:table-cell">{p.messages}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCents(p.available_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )
      ) : clients.length === 0 ? (
        <EmptyState title="Ningún cliente coincide" readonly />
      ) : (
        <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cliente</TableHead>
                <TableHead className="text-right">Gasto</TableHead>
                <TableHead className="hidden text-right lg:table-cell">Coste interno</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Mensajes</TableHead>
                <TableHead className="hidden text-right md:table-cell">Conversaciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.map((c) => (
                <TableRow key={c.tenant_id} className="relative hover:bg-muted/50">
                  <TableCell>
                    <Link
                      href={`/tenants/${c.tenant_id}`}
                      className="flex flex-col gap-1 outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
                    >
                      <span className="font-medium">{c.name}</span>
                      <span className="text-xs text-muted-foreground">{c.partner_name ?? "Auphere directo"}</span>
                    </Link>
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {c.partner_id ? formatCents(c.spend_cents) : <span className="text-muted-foreground">Sin saldo</span>}
                  </TableCell>
                  <TableCell className="hidden text-right text-muted-foreground tabular-nums lg:table-cell">
                    {formatUsd(c.internal_cost_usd)}
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums sm:table-cell">
                    {c.messages_inbound + c.messages_outbound}
                    <span className="sr-only">
                      {" "}
                      ({c.messages_inbound} recibidos, {c.messages_outbound} enviados)
                    </span>
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums md:table-cell">{c.conversations}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
