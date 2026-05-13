"use server";

import { revalidatePath } from "next/cache";

import {
  backend,
  BackendError,
  type AgentConfig,
  type ImprovePromptMode,
  type ImprovePromptOut,
  type TestAgentHistoryMessage,
  type TestTurnOut,
} from "@/lib/backend";
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

export async function improveAgentPromptAction(
  tenantId: string,
  body: {
    prompt: string;
    mode?: ImprovePromptMode;
    feedback?: string | null;
  },
): Promise<Result<ImprovePromptOut>> {
  await requireSession();
  try {
    const result = await backend.improveAgentPrompt(tenantId, body);
    // We deliberately do NOT revalidatePath here: the improver returns
    // text the operator may apply or discard. Re-render happens after
    // the operator clicks "Aplicar" and saves a new draft via stage.
    return { ok: true, data: result! };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}


export async function testAgentTurnAction(
  tenantId: string,
  body: {
    user_message: string;
    history?: TestAgentHistoryMessage[];
    version?: number;
  },
): Promise<Result<TestTurnOut>> {
  await requireSession();
  try {
    const result = await backend.testAgentTurn(tenantId, body);
    // The sandbox doesn't mutate any persistent state — no
    // revalidatePath. Chat history lives in the dialog's local state.
    return { ok: true, data: result! };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}


export async function applySeedTemplateAction(
  tenantId: string,
  body: { seed_template_ref: string; placeholders: Record<string, unknown> },
): Promise<Result<AgentConfig>> {
  await requireSession();
  try {
    const result = await backend.applyAgentConfigSeed(tenantId, body);
    revalidatePath(`/tenants/${tenantId}/agent`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: result! };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}
