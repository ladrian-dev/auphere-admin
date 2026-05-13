"use server";

/**
 * Block M.3 — conversation lifecycle server actions.
 *
 * The toggle drives a one-line PATCH against the backend. We revalidate
 * both the list path AND the detail path (when present) so the operator
 * sees the new state immediately regardless of where they clicked.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend } from "@/lib/backend";

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

function err(e: unknown): { ok: false; error: string } {
  if (e instanceof BackendError) {
    const body = e.body as { detail?: string } | null;
    return { ok: false, error: body?.detail ?? `HTTP ${e.status}` };
  }
  return { ok: false, error: e instanceof Error ? e.message : String(e) };
}

export async function toggleConversationAgentAction(
  tenantId: string,
  conversationId: string,
  agentActive: boolean,
): Promise<ActionResult<{ agent_active: boolean }>> {
  try {
    const r = await backend.toggleConversationAgent(
      tenantId,
      conversationId,
      agentActive,
    );
    if (!r) return { ok: false, error: "empty response" };
    revalidatePath(`/tenants/${tenantId}/conversations`);
    revalidatePath(`/tenants/${tenantId}/conversations/${conversationId}`);
    return { ok: true, data: { agent_active: r.agent_active } };
  } catch (e) {
    return err(e);
  }
}
