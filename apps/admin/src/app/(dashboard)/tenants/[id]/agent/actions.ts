"use server";

import { revalidatePath } from "next/cache";

import { backend, BackendError, type AgentConfig } from "@/lib/backend";
import { requireSession } from "@/lib/session";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function pluck(err: unknown): string {
  if (err instanceof BackendError) {
    if (typeof err.body === "object" && err.body && "detail" in err.body) {
      return String((err.body as { detail: unknown }).detail);
    }
    return `error ${err.status}`;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

export async function stageAgentConfigAction(
  tenantId: string,
  body: {
    system_prompt_rendered: string;
    channels: Array<Record<string, unknown>>;
    tools: string[];
    policies: Record<string, unknown>;
    seed_template_ref?: string | null;
    kg_schema_id?: string | null;
  },
): Promise<Result<AgentConfig>> {
  await requireSession();
  try {
    const result = await backend.stageAgentConfig(tenantId, body);
    revalidatePath(`/tenants/${tenantId}/agent`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: result! };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}

export async function promoteAgentConfigAction(
  tenantId: string,
  version: number,
): Promise<Result<AgentConfig>> {
  await requireSession();
  try {
    const result = await backend.promoteAgentConfig(tenantId, version);
    revalidatePath(`/tenants/${tenantId}/agent`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: result! };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}

export async function rollbackAgentConfigAction(
  tenantId: string,
  version: number,
): Promise<Result<AgentConfig>> {
  await requireSession();
  try {
    const result = await backend.rollbackAgentConfig(tenantId, version);
    revalidatePath(`/tenants/${tenantId}/agent`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: result! };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}
