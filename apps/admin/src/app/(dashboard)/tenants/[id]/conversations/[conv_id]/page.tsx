import Link from "next/link";
import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import { MessageBubble } from "@/components/conversation/message-bubble";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend } from "@/lib/backend";
import { relativeTime, statusLabel } from "@/lib/format";

import { TakeoverPanel } from "./takeover-panel";

const STATUS_TONE = {
  open: "info",
  closed: "muted",
  escalated: "danger",
} as const;

/**
 * Block M.3 — conversation detail view.
 *
 * Renders the full message history (ordered chronologically) and surfaces
 * the per-conversation agent toggle. The header shows who's currently
 * driving the thread (agent vs operator) so a glance answers "should I
 * be answering this customer right now?".
 *
 * Not real-time yet — Phase 2 wires SSE per-message updates. Today the
 * operator refreshes after replying via WhatsApp.
 */
export default async function ConversationDetailPage({
  params,
}: {
  params: Promise<{ id: string; conv_id: string }>;
}) {
  const { id, conv_id } = await params;
  const [tenant, conversation, messages] = await Promise.all([
    backend.getTenant(id),
    backend.getConversation(id, conv_id),
    backend.listConversationMessages(id, conv_id),
  ]);
  if (!tenant || !conversation) notFound();

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div className="flex flex-col gap-1">
              <Eyebrow>Conversación</Eyebrow>
              <CardTitle className="font-mono text-base md:text-lg">
                {conversation.id.slice(0, 8)} ·{" "}
                <span className="text-muted-foreground">
                  customer {conversation.customer_id.slice(0, 8)}
                </span>
              </CardTitle>
              <CardDescription className="flex items-center gap-4 text-sm">
                <span className="inline-flex items-center gap-2">
                  <StatusDot tone={STATUS_TONE[conversation.status]} />
                  {statusLabel(conversation.status)}
                </span>
                <span>Abierta {relativeTime(conversation.created_at)}</span>
                <span>· Última actividad {relativeTime(conversation.updated_at)}</span>
              </CardDescription>
            </div>
            <Link
              href={`/tenants/${tenant.id}/conversations`}
              className="text-xs text-muted-foreground hover:text-foreground underline-offset-4 hover:underline decoration-1"
            >
              ← Lista
            </Link>
          </div>
        </CardHeader>
        <CardContent className="border-t border-border pt-4">
          <TakeoverPanel
            tenantId={tenant.id}
            conversationId={conversation.id}
            agentActive={conversation.agent_active}
            agentActiveVersion={conversation.agent_active_version}
            takeoverContext={conversation.takeover_context}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Historial</Eyebrow>
          <CardTitle>Mensajes ({messages.length})</CardTitle>
          <CardDescription>
            Orden cronológico. Los azules son del cliente, los grises del
            agente. Reactivar el agente NO desencadena auto-reply al
            backlog — solo afecta el próximo turno.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              Sin mensajes todavía.
            </p>
          ) : (
            messages.map((m) => <MessageBubble key={m.id} message={m} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}
