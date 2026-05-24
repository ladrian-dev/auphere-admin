"use server";

/**
 * Block M.3 + Bloque C — conversation lifecycle server actions.
 *
 * The toggle drives a one-line PATCH against the backend. We revalidate
 * both the list path AND the detail path (when present) so the operator
 * sees the new state immediately regardless of where they clicked.
 *
 * Bloque C adds: optional ``reason`` / ``notes`` + optimistic-locking
 * ``expectedVersion`` for the toggle, and a separate
 * ``operatorSendMessageAction`` for the operator-side reply.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend } from "@/lib/backend";

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string }
  | { ok: false; error: string; conflict: true };

function err(e: unknown): { ok: false; error: string } {
  if (e instanceof BackendError) {
    const body = e.body as { detail?: unknown } | null;
    const detail = body?.detail;
    if (typeof detail === "string") return { ok: false, error: detail };
    if (detail && typeof detail === "object") {
      const d = detail as { message?: string; error?: string };
      return { ok: false, error: d.message ?? d.error ?? `HTTP ${e.status}` };
    }
    return { ok: false, error: `HTTP ${e.status}` };
  }
  return { ok: false, error: e instanceof Error ? e.message : String(e) };
}

export async function toggleConversationAgentAction(
  tenantId: string,
  conversationId: string,
  agentActive: boolean,
  opts?: {
    reason?: string | null;
    notes?: string | null;
    expectedVersion?: number;
  },
): Promise<
  ActionResult<{
    agent_active: boolean;
    agent_active_version: number;
  }>
> {
  try {
    const r = await backend.toggleConversationAgent(
      tenantId,
      conversationId,
      agentActive,
      opts,
    );
    if (!r) return { ok: false, error: "empty response" };
    revalidatePath(`/tenants/${tenantId}/conversations`);
    revalidatePath(`/tenants/${tenantId}/conversations/${conversationId}`);
    return {
      ok: true,
      data: {
        agent_active: r.agent_active,
        agent_active_version: r.agent_active_version,
      },
    };
  } catch (e) {
    if (e instanceof BackendError && e.status === 412) {
      return {
        ok: false,
        conflict: true,
        error: "Otro operador modificó esta conversación. Recargá y reintentá.",
      };
    }
    return err(e);
  }
}

export async function operatorSendMessageAction(
  tenantId: string,
  conversationId: string,
  content: string,
): Promise<ActionResult<{ message_id: string }>> {
  try {
    const r = await backend.operatorSendMessage(
      tenantId,
      conversationId,
      content,
    );
    if (!r) return { ok: false, error: "empty response" };
    revalidatePath(`/tenants/${tenantId}/conversations/${conversationId}`);
    return { ok: true, data: { message_id: r.id } };
  } catch (e) {
    return err(e);
  }
}
