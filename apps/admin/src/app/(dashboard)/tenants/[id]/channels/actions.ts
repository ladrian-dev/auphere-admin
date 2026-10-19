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

/** Spec 040: a link for the business owner to connect WhatsApp on their device. */
export async function createSignupLinkAction(
  tenantId: string,
  mode: "coexistence" | "cloud_api",
): Promise<Result<{ url: string; expires_at: string }>> {
  const operator = await requireOperator();
  try {
    const link = await backend.createSignupLink(tenantId, mode, operator.id);
    if (!link?.url) return { ok: false, error: "La API no devolvió el enlace." };
    revalidatePath(`/tenants/${tenantId}/channels`);
    return { ok: true, data: { url: link.url, expires_at: link.expires_at } };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function revokeSignupLinkAction(tenantId: string, linkId: string): Promise<Result<null>> {
  const operator = await requireOperator();
  try {
    await backend.revokeSignupLink(tenantId, linkId, operator.id);
    revalidatePath(`/tenants/${tenantId}/channels`);
    return { ok: true, data: null };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
