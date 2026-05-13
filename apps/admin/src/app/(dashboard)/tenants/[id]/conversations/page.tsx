import Link from "next/link";

import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
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
import { fullDateTime, relativeTime, statusLabel } from "@/lib/format";

import { AgentToggle } from "./agent-toggle";
import { LiveIndicator } from "./live-indicator";

const STATUS_TONE = {
  open: "info",
  closed: "muted",
  escalated: "danger",
} as const;

export default async function ConversationsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, page] = await Promise.all([
    backend.getTenant(id),
    backend.listConversations(id, undefined, 50),
  ]);
  if (!tenant) return null;

  const escalated = page.items.filter((c) => c.status === "escalated").length;
  const open = page.items.filter((c) => c.status === "open").length;
  const takenOver = page.items.filter((c) => c.agent_active === false).length;

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <Eyebrow>Conversaciones</Eyebrow>
              <CardTitle className="flex items-center gap-3">
                Historial reciente
                <LiveIndicator tenantId={tenant.id} />
              </CardTitle>
              <CardDescription>
                Las últimas {page.items.length} conversaciones del tenant. El
                indicador en vivo escucha el stream del backend.
              </CardDescription>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span className="inline-flex items-center gap-2">
                <StatusDot tone="info" />
                <span>
                  <strong className="tabular-nums text-foreground">{open}</strong> abiertas
                </span>
              </span>
              {escalated > 0 ? (
                <span className="inline-flex items-center gap-2">
                  <StatusDot tone="danger" pulse />
                  <span>
                    <strong className="tabular-nums text-foreground">{escalated}</strong> escaladas
                  </span>
                </span>
              ) : null}
              {takenOver > 0 ? (
                <span className="inline-flex items-center gap-2">
                  <StatusDot tone="warning" />
                  <span>
                    <strong className="tabular-nums text-foreground">{takenOver}</strong> con operador
                  </span>
                </span>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {page.items.length === 0 ? (
            <div className="px-6 py-12 text-center text-muted-foreground text-sm">
              Sin conversaciones todavía. Cuando llegue el primer mensaje al webhook YCloud aparecerán acá.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Conversación</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Agente</TableHead>
                  <TableHead className="hidden md:table-cell">Abierta</TableHead>
                  <TableHead className="text-right">Última actividad</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.items.map((conv) => (
                  <TableRow key={conv.id} className="hover:bg-muted/40">
                    <TableCell>
                      <Link
                        href={`/tenants/${tenant.id}/conversations/${conv.id}`}
                        className="flex flex-col outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                      >
                        <span className="font-mono text-sm">
                          {conv.id.slice(0, 8)}
                        </span>
                        <span className="text-xs text-muted-foreground font-mono">
                          customer {conv.customer_id.slice(0, 8)}
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2">
                        <StatusDot tone={STATUS_TONE[conv.status]} />
                        {statusLabel(conv.status)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <AgentToggle
                        tenantId={tenant.id}
                        conversationId={conv.id}
                        agentActive={conv.agent_active}
                      />
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-muted-foreground">
                      {fullDateTime(conv.created_at)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {relativeTime(conv.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
