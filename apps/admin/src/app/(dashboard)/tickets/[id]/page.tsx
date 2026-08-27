import Link from "next/link";
import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { PageHeader } from "@/components/brand/page-header";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

import { TicketStatusForm } from "./status-form";

const LINK_LABELS = [
  { key: "consumo" as const, label: "Consumo" },
  { key: "modelos" as const, label: "Modelos" },
  { key: "conocimiento" as const, label: "Conocimiento" },
];

/**
 * Detalle F4 — estado PATCH + deep-links a las pestañas del partner.
 */
export default async function TicketDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const ticket = await backend.getTicket(id);
  if (!ticket) notFound();

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Soporte"
        title={ticket.ticket_ref}
        description={
          <>
            {ticket.partner_name}{" "}
            <span className="font-mono text-xs">({ticket.partner_slug})</span>
          </>
        }
        actions={
          <Link
            href={`/partners/${ticket.partner_id}`}
            className="text-sm text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
          >
            Ir al partner
          </Link>
        }
      />

      <Card>
        <CardHeader>
          <Eyebrow>Ticket</Eyebrow>
          <CardTitle>{ticket.topic}</CardTitle>
          <CardDescription>
            {ticket.category} · SLA {ticket.sla}
            {ticket.client_ref ? ` · cliente ${ticket.client_ref}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <p className="text-sm whitespace-pre-wrap">{ticket.need}</p>
          {ticket.checked.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {ticket.checked.map((item) => (
                <li key={item} className="font-mono text-xs">
                  {item}
                </li>
              ))}
            </ul>
          ) : null}
          {ticket.alternative ? (
            <p className="text-sm text-muted-foreground">
              Alternativa{ticket.bridge ? " (puente)" : ""}: {ticket.alternative}
            </p>
          ) : null}
          <TicketStatusForm ticketId={ticket.id} status={ticket.status} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Partner</Eyebrow>
          <CardTitle>Pestañas del partner</CardTitle>
          <CardDescription>
            Consumo, Modelos y Conocimiento del partner.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          {LINK_LABELS.map((item) => (
            <Link
              key={item.key}
              href={ticket.links[item.key]}
              className="rounded-md border border-border px-3 py-2 text-sm hover:bg-muted/40"
            >
              {item.label}
            </Link>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Eventos</Eyebrow>
          <CardTitle>Historial</CardTitle>
        </CardHeader>
        <CardContent>
          {ticket.events.length === 0 ? (
            <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
              Sin eventos.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cuándo</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>De → A</TableHead>
                    <TableHead>Actor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ticket.events.map((ev) => (
                    <TableRow key={ev.id}>
                      <TableCell className="tabular-nums text-xs">
                        {relativeTime(ev.created_at)}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{ev.kind}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {ev.from_status ?? "—"} → {ev.to_status}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {ev.actor}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
