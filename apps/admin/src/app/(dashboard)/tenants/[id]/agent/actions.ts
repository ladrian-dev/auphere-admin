"use server";

import { revalidatePath } from "next/cache";

import {
  backend,
  BackendError,
  type AgentConfig,
  type ImprovePromptMode,
  type ImprovePromptOut,
  type PromptSnippet,
  type RuntimeCapabilitiesInput,
  type SeedTemplateMetrics,
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

/** Update the 5 runtime fields of a STAGED agent_config (memory tool,
 *  outcome grader, mcp connector booleans + skills/mcp_servers lists).
 *  The backend refuses non-STAGED versions — capability changes are
 *  versioned through the STAGED → ACTIVE flow. */
export async function updateRuntimeCapabilitiesAction(
  tenantId: string,
  version: number,
  body: RuntimeCapabilitiesInput,
): Promise<Result<AgentConfig>> {
  await requireSession();
  try {
    const result = await backend.updateRuntimeCapabilities(
      tenantId,
      version,
      body,
    );
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


// ── Block Q — Prompt library + seed metrics (client-side reads) ──────────
//
// Client components can't reach ``@/lib/backend`` directly because that
// module declares ``import "server-only"`` to keep the admin token out
// of the browser bundle. These thin server actions proxy the reads so
// the SeedMetricsBadge and InsertPatternButton dialogs work from the
// client without leaking credentials.

export async function getSeedMetricsAction(
  templateName: string,
): Promise<Result<SeedTemplateMetrics | null>> {
  await requireSession();
  try {
    const result = await backend.getSeedTemplateMetrics(templateName);
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}

export async function listPromptLibraryAction(
  opts: { vertical?: string; category?: string } = {},
): Promise<Result<PromptSnippet[]>> {
  await requireSession();
  try {
    const result = await backend.listPromptLibrary(opts);
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: pluck(err) };
  }
}
