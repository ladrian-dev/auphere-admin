import Link from "next/link";
import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { backend, type MessageOut } from "@/lib/backend";
import { fullDateTime, relativeTime, statusLabel } from "@/lib/format";

import { AgentToggle } from "../agent-toggle";

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
            <div className="flex items-center gap-2">
              <Link
                href={`/tenants/${tenant.id}/conversations`}
                className="text-xs text-muted-foreground hover:text-foreground underline-offset-4 hover:underline decoration-1"
              >
                ← Lista
              </Link>
              <AgentToggle
                tenantId={tenant.id}
                conversationId={conversation.id}
                agentActive={conversation.agent_active}
                variant="button"
              />
            </div>
          </div>
        </CardHeader>
        {!conversation.agent_active ? (
          <CardContent className="border-t border-border pt-4">
            <div className="rounded-md border border-amber-300/40 bg-amber-50/40 dark:bg-amber-950/20 px-4 py-3 text-sm">
              <strong>Operador en control de este thread.</strong>{" "}
              El agente no responde mensajes nuevos en esta conversación hasta
              que clickees <em>Reactivar agente</em>. Los mensajes entrantes
              siguen apareciendo abajo para que puedas atenderlos manualmente.
            </div>
          </CardContent>
        ) : null}
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
            messages.map((m) => <MessageRow key={m.id} message={m} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function MessageRow({ message }: { message: MessageOut }) {
  const inbound = message.direction === "inbound";
  return (
    <div
      className={
        "flex flex-col gap-1 rounded-md px-3 py-2 border border-border " +
        (inbound ? "bg-blue-50/50 dark:bg-blue-950/20" : "bg-muted/40")
      }
    >
      <div className="flex items-center justify-between text-[10px] font-mono uppercase text-muted-foreground tabular-nums">
        <span style={{ letterSpacing: "var(--tracking-eyebrow)" }}>
          {inbound ? "← Cliente" : "→ Agente"}
          {message.intent ? ` · ${message.intent}` : ""}
          {message.model ? ` · ${message.model}` : ""}
        </span>
        <span>{fullDateTime(message.created_at)}</span>
      </div>
      <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
      {message.tool_calls.length > 0 ? (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">
            {message.tool_calls.length} tool call
            {message.tool_calls.length === 1 ? "" : "s"}
          </summary>
          <pre className="mt-1 overflow-x-auto rounded bg-muted/60 p-2 text-[11px]">
            {JSON.stringify(message.tool_calls, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
