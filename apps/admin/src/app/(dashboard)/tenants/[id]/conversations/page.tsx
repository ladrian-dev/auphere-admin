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
                Las últimas {page.items.length} conversaciones del tenant. La señal en vivo se
                conecta al stream del backend; si falla, hay polling como fallback (Phase 2).
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
                  <TableHead>Abierta</TableHead>
                  <TableHead className="text-right">Última actividad</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.items.map((conv) => (
                  <TableRow key={conv.id}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-mono text-sm">
                          {conv.id.slice(0, 8)}
                        </span>
                        <span className="text-xs text-muted-foreground font-mono">
                          customer {conv.customer_id.slice(0, 8)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2">
                        <StatusDot tone={STATUS_TONE[conv.status]} />
                        {statusLabel(conv.status)}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
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
