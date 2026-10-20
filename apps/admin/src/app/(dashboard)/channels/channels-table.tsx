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

import { ChannelLogo } from "@/components/brand/channel-logo";
import { CHANNEL_NAME, CHANNEL_STATUS, ROLE_LABEL } from "@/components/channels/labels";
import type { GlobalChannel } from "@/lib/backend";
import { relativeTime } from "@/lib/format";
import { filterRows } from "@/lib/list-filter";

/** Spec 035 (R3): every client's channels in one list, with search and filters. */
export function ChannelsTable({ channels }: { channels: GlobalChannel[] }) {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const types = useMemo(() => [...new Set(channels.map((c) => c.type))].sort(), [channels]);
  const rows = useMemo(
    () =>
      filterRows(
        channels,
        q,
        (c) => [c.name, c.tenant_name, c.partner_name ?? "Auphere directo", c.provider_identifier],
        [
          { value: type, of: (c) => c.type },
          { value: status, of: (c) => c.status },
        ],
      ),
    [channels, q, type, status],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          aria-label="Buscar canales"
          placeholder="Buscar por cliente, partner o número…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="sm:max-w-xs"
        />
        <NativeSelect aria-label="Tipo de canal" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Todos los tipos</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {CHANNEL_NAME[t] ?? t}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Estado" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Todos los estados</option>
          {Object.entries(CHANNEL_STATUS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <p className="text-xs text-muted-foreground tabular-nums">
        {rows.length} de {channels.length} canales
      </p>
      {rows.length === 0 ? (
        <EmptyState title="Ningún canal coincide" description="Cambia la búsqueda o los filtros." readonly />
      ) : (
        <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Canal</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Partner</TableHead>
                <TableHead>Papel</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Conectado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => {
                const st = CHANNEL_STATUS[c.status] ?? { label: c.status, tone: "muted" as const };
                return (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Link
                        href={`/tenants/${c.tenant_id}/channels/${c.id}`}
                        className="flex items-center gap-3 hover:underline"
                      >
                        <ChannelLogo channel={c.type} size="sm" />
                        <span className="flex min-w-0 flex-col">
                          <span className="truncate text-sm font-medium">{c.name ?? CHANNEL_NAME[c.type] ?? c.type}</span>
                          <span className="truncate font-mono text-xs text-muted-foreground">{c.provider_identifier}</span>
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link href={`/tenants/${c.tenant_id}`} className="hover:underline">
                        {c.tenant_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.partner_id ? (
                        <Link href={`/partners/${c.partner_id}`} className="hover:underline">
                          {c.partner_name}
                        </Link>
                      ) : (
                        "Auphere directo"
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.role ? ROLE_LABEL[c.role] ?? c.role : "—"}
                      {c.agent_enabled ? "" : " · agente en silencio"}
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2">
                        <StatusDot tone={st.tone} />
                        {st.label}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{relativeTime(c.created_at)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
