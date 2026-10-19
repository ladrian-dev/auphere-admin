"use server";

import { revalidatePath } from "next/cache";

import { BackendError, backend } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function toError(err: unknown): string {
  if (err instanceof BackendError) {
    const body = err.body as { detail?: unknown } | null;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "code" in detail) return String((detail as { code: unknown }).code);
    return `Error ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}

/** Spec 035: which of the client's agents answers on a channel. The operator signs it. */
export async function assignChannelAgentAction(
  tenantId: string,
  channelId: string,
  agentId: string,
): Promise<Result<null>> {
  const operator = await requireOperator();
  try {
    await backend.assignChannelAgent(tenantId, channelId, agentId, operator.id);
    revalidatePath(`/tenants/${tenantId}`, "layout");
    return { ok: true, data: null };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
