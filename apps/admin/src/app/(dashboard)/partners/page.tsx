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
import { relativeTime, statusLabel } from "@/lib/format";

export const metadata = { title: "Partners" };

const STATUS_TONE: Record<string, "positive" | "danger" | "muted"> = {
  active: "positive",
  suspended: "danger",
};

/**
 * Partner platform index (ADR-028). Each partner is a SaaS company that
 * embeds the WhatsApp widget in its own product — they authenticate
 * server-to-server with secret API keys, never with the admin token.
 */
export default async function PartnersPage() {
  const partners = await backend.listPartners();
  const counts = {
    total: partners.length,
    active: partners.filter((p) => p.status === "active").length,
    suspended: partners.filter((p) => p.status === "suspended").length,
  };

  return (
    <>
      <PageHeader
        eyebrow="Partners"
        title="Plataforma de partners"
        description="Empresas SaaS que embeben el widget de WhatsApp vía API keys secretas. Click en una fila para gestionar keys, origins y límites."
        actions={
          <Button render={<Link href="/partners/new" />}>Nuevo partner</Button>
        }
      />

      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <span>
          <strong className="text-foreground tabular-nums">
            {counts.total}
          </strong>{" "}
          partners
        </span>
        <span>
          <strong className="text-foreground tabular-nums">
            {counts.active}
          </strong>{" "}
          activos
        </span>
        {counts.suspended > 0 ? (
          <span>
            <strong className="text-foreground tabular-nums">
              {counts.suspended}
            </strong>{" "}
            suspendidos
          </span>
        ) : null}
      </div>

      <div className="rounded-md border border-border bg-card overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Partner</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="hidden sm:table-cell text-right">
                Cap broadcast
              </TableHead>
              <TableHead className="hidden md:table-cell text-right">
                Creado
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {partners.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={4}
                  className="py-12 text-center text-muted-foreground"
                >
                  Sin partners todavía. Crea el primero con &quot;Nuevo
                  partner&quot; arriba a la derecha.
                </TableCell>
              </TableRow>
            ) : (
              partners.map((partner) => (
                <TableRow
                  key={partner.id}
                  className="transition-colors hover:bg-muted/40"
                >
                  <TableCell>
                    <Link
                      href={`/partners/${partner.id}`}
                      className="flex flex-col gap-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                    >
                      <span className="font-medium">{partner.name}</span>
                      <span className="text-xs font-mono text-muted-foreground">
                        {partner.slug}
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-2">
                      <StatusDot
                        tone={STATUS_TONE[partner.status] ?? "muted"}
                      />
                      <span>{statusLabel(partner.status)}</span>
                    </span>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell text-right">
                    <Badge variant="outline" className="tabular-nums">
                      {partner.broadcast_recipient_cap} destinatarios
                    </Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-right text-muted-foreground tabular-nums">
                    {relativeTime(partner.created_at)}
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
