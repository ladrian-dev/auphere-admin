import Link from "next/link";

import {
  EmptyState,
  Section,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import { backend } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";

import { AgentToggle } from "./agent-toggle";
import { LiveIndicator } from "./live-indicator";

const STATUS_TONE = { open: "info", closed: "muted", escalated: "danger" } as const;
const STATUS_LABEL = { open: "Abierta", closed: "Resuelta", escalated: "Escalada" } as const;

/**
 * Spec 036: the client's conversations, by the person who wrote (H2: names,
 * not ids), newest activity first, with who answers and the way to take over
 * said in words.
 */
export default async function ConversationsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [tenant, page] = await Promise.all([backend.getTenant(id), backend.listConversations(id, undefined, 50)]);
  if (!tenant) return null;

  const escalated = page.items.filter((c) => c.status === "escalated").length;
  const open = page.items.filter((c) => c.status === "open").length;
  const takenOver = page.items.filter((c) => c.agent_active === false).length;

  return (
    <Section
      title={
        <span className="flex items-center gap-3">
          Conversaciones
          <LiveIndicator tenantId={tenant.id} />
        </span>
      }
      description={`Las ${page.items.length} más recientes. Pulsa una para leerla o responder.`}
      actions={
        <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <StatusDot tone="info" />
            <span>
              <strong className="text-foreground tabular-nums">{open}</strong> abiertas
            </span>
          </span>
          {escalated > 0 ? (
            <span className="inline-flex items-center gap-2">
              <StatusDot tone="danger" pulse />
              <span>
                <strong className="text-foreground tabular-nums">{escalated}</strong> escaladas
              </span>
            </span>
          ) : null}
          {takenOver > 0 ? (
            <span className="inline-flex items-center gap-2">
              <StatusDot tone="warning" />
              <span>
                <strong className="text-foreground tabular-nums">{takenOver}</strong> con una persona
              </span>
            </span>
          ) : null}
        </div>
      }
      padded={false}
    >
      {page.items.length === 0 ? (
        <EmptyState
          title="Todavía nadie ha escrito"
          description="Cuando llegue el primer mensaje por un canal del cliente aparecerá aquí."
          readonly
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Contacto</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Responde</TableHead>
              <TableHead className="hidden md:table-cell">Empezó</TableHead>
              <TableHead className="text-right">Último mensaje</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((conv) => (
              <TableRow key={conv.id} className="relative hover:bg-muted/50">
                <TableCell>
                  <Link
                    href={`/tenants/${tenant.id}/conversations/${conv.id}`}
                    className="flex flex-col gap-1 outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
                  >
                    <span className="text-sm font-medium">
                      {conv.customer_name || conv.customer_identifier || "Contacto sin número"}
                    </span>
                    {conv.customer_name && conv.customer_identifier ? (
                      <span className="font-mono text-xs text-muted-foreground">{conv.customer_identifier}</span>
                    ) : null}
                  </Link>
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-2 text-sm">
                    <StatusDot tone={STATUS_TONE[conv.status]} />
                    {STATUS_LABEL[conv.status]}
                  </span>
                </TableCell>
                <TableCell className="relative z-10">
                  {conv.status === "closed" ? (
                    // A resolved conversation has nobody to answer: no control to offer.
                    <span className="text-sm text-muted-foreground">—</span>
                  ) : (
                    <AgentToggle tenantId={tenant.id} conversationId={conv.id} agentActive={conv.agent_active} />
                  )}
                </TableCell>
                <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
                  {fullDateTime(conv.created_at)}
                </TableCell>
                <TableCell className="text-right text-sm text-muted-foreground tabular-nums">
                  {relativeTime(conv.last_message_at ?? conv.updated_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Section>
  );
}
