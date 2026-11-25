"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import { BackendError } from "@/lib/backend";
import { modelsBackend, type AgentModelView } from "@/lib/backend-models";
import { requireOperator } from "@/lib/session";

/** Spec 030: an id goes into a URL — only a UUID gets there. */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Spec 065 (`contracts/api.md`): the refusals of `PUT …/agents/{agent_id}/model`, in words. */
const WORDS: Record<string, string> = {
  unknown_model: "No se pudo cambiar el modelo: ese modelo ya no está habilitado para responder. Recarga la página y elige otro.",
  model_unavailable_for_agent:
    "No se pudo cambiar el modelo: ese modelo no puede ejecutar lo que usa este agente (Skills o un conector MCP de Anthropic). Elige otro.",
};

/**
 * Spec 065 (T075; requisito 7.2): Auphere chooses the model of one agent among
 * the ones enabled to answer, in the partner's list or not, with its reason;
 * `null` goes back to Auphere's default. The API writes `set_by = 'operator'`,
 * audits the operator and the reason, and the agent answers with it from its
 * next message.
 */
export async function setAgentModelAction(
  tenantId: string,
  agentId: string,
  modelId: string | null,
  reason: string,
): Promise<Result<AgentModelView>> {
  const operator = await requireOperator("operate");
  if (!UUID_RE.test(tenantId) || !UUID_RE.test(agentId)) return { ok: false, error: "Ese agente no existe." };
  const why = reason.trim();
  if (!why) return { ok: false, code: "reason_required", error: "Hace falta el motivo." };
  try {
    const data = await modelsBackend.setAgentModel(tenantId, agentId, { model_id: modelId, reason: why }, operator.id);
    revalidatePath(`/tenants/${tenantId}/agent`);
    return { ok: true, data: data as AgentModelView };
  } catch (err) {
    if (err instanceof BackendError && err.status === 404) {
      return { ok: false, error: "Ese agente ya no está activo. Recarga la página." };
    }
    return toFailure(err, WORDS);
  }
}
