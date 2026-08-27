import Link from "next/link";

import { PageHeader } from "@/components/brand/page-header";
import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { backend } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

export const metadata = { title: "Tickets" };

const STATUS_TONE: Record<string, "positive" | "danger" | "muted"> = {
  open: "danger",
  pending: "muted",
  closed: "positive",
};

const STATUS_LABEL: Record<string, string> = {
  open: "Abierto",
  pending: "Pendiente",
  closed: "Cerrado",
};

/**
 * Inbox F4 — tickets de todos los partners. Sin estado en consola.
 * El POST que los crea sigue siendo /console/support/tickets.
 */
export default async function TicketsPage() {
  const tickets = await backend.listTickets();
  const counts = {
    total: tickets.length,
    open: tickets.filter((t) => t.status === "open").length,
    pending: tickets.filter((t) => t.status === "pending").length,
  };

  return (
    <>
      <PageHeader
        eyebrow="Soporte"
        title="Tickets de partners"
        description="Bandeja de la plataforma. Los tickets los abre el partner en la consola; aquí se leen y se cierra el estado."
      />

      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <span>
          <strong className="text-foreground tabular-nums">{counts.total}</strong>{" "}
          tickets
        </span>
        <span>
          <strong className="text-foreground tabular-nums">{counts.open}</strong>{" "}
          abiertos
        </span>
        {counts.pending > 0 ? (
          <span>
            <strong className="text-foreground tabular-nums">
              {counts.pending}
            </strong>{" "}
            pendientes
          </span>
        ) : null}
      </div>

      <div className="rounded-md border border-border bg-card overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ref</TableHead>
              <TableHead>Partner</TableHead>
              <TableHead>Tema</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="hidden md:table-cell text-right">
                Abierto
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tickets.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-12 text-center text-muted-foreground"
                >
                  Sin tickets. Cuando un partner confirme un escalado en la
                  consola, aparece aquí.
                </TableCell>
              </TableRow>
            ) : (
              tickets.map((ticket) => (
                <TableRow
                  key={ticket.id}
                  className="transition-colors hover:bg-muted/40"
                >
                  <TableCell>
                    <Link
                      href={`/tickets/${ticket.id}`}
                      className="font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                    >
                      {ticket.ticket_ref}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <Link
                        href={`/partners/${ticket.partner_id}`}
                        className="flex flex-col gap-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                      >
                        <span className="font-medium">{ticket.partner_name}</span>
                        <span className="text-xs font-mono text-muted-foreground">
                          {ticket.partner_slug}
                        </span>
                      </Link>
                      <span className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <Link href={`/partners/${ticket.partner_id}/wallet`} className="hover:underline">
                          Consumo
                        </Link>
                        <Link href={`/partners/${ticket.partner_id}/models`} className="hover:underline">
                          Modelos
                        </Link>
                        <Link href={`/partners/${ticket.partner_id}/knowledge`} className="hover:underline">
                          Conocimiento
                        </Link>
                        <Link href={`/partners/${ticket.partner_id}/audit`} className="hover:underline">
                          Auditoría
                        </Link>
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-col gap-0.5">
                      <span className="font-mono text-xs">{ticket.topic}</span>
                      <Badge variant="outline" className="w-fit">
                        {ticket.category}
                      </Badge>
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-2">
                      <StatusDot tone={STATUS_TONE[ticket.status] ?? "muted"} />
                      <span>{STATUS_LABEL[ticket.status] ?? ticket.status}</span>
                    </span>
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-right text-muted-foreground tabular-nums">
                    {relativeTime(ticket.opened_at)}
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
