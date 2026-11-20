"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Failure, type Result } from "@/lib/action-result";
import { BackendError } from "@/lib/backend";
import {
  modelsBackend,
  type DeploymentIn,
  type DeploymentRow,
  type PriceIn,
  type ProposalOut,
  type RespondDefault,
  type RespondDefaultAffected,
  type SalePolicy,
  type SalePolicyIn,
  type WeightsIn,
} from "@/lib/backend-models";
import { requireOperator } from "@/lib/session";

import { ERRORS, POLICY_ERRORS, PRICE_ERRORS, refusalWords } from "./labels";

/**
 * Spec 047 (T150) and spec 059: the catalog's writes. Each one carries the
 * operator of the panel session and its reason; the API audits both and the
 * change applies from the next turn.
 */

/** The API's `detail`, when it carries a code (`{"detail": {"code": …}}`). */
function detailOf(err: unknown): ({ code: string } & Record<string, unknown>) | null {
  if (!(err instanceof BackendError)) return null;
  const body = err.body;
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail !== "object" || detail === null || !("code" in detail)) return null;
  return { ...(detail as Record<string, unknown>), code: String((detail as { code: unknown }).code) };
}

/**
 * A refusal in words: the detail's own sentence when it has one (contrato §2,
 * §6), else the action's table. The multiplier's `below_floor` carries no
 * lanes, so its sentence is the table's.
 */
function refusal(err: unknown, words: Record<string, string>): Failure {
  const failure = toFailure(err, words);
  const detail = detailOf(err);
  const sentence = detail ? refusalWords(detail) : null;
  return sentence ? { ...failure, error: sentence } : failure;
}

async function guarded<T>(
  fn: (operatorId: string) => Promise<T | null>,
  words: Record<string, string> = ERRORS,
): Promise<Result<T>> {
  const operator = await requireOperator();
  try {
    const data = await fn(operator.id);
    revalidatePath("/models");
    return { ok: true, data: data as T };
  } catch (err) {
    return refusal(err, words);
  }
}

export async function createDeploymentAction(body: DeploymentIn): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.createDeployment(body, op));
}

export async function activateAction(uuid: string, reason: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.activate(uuid, reason, op));
}

export async function addPriceAction(uuid: string, body: PriceIn): Promise<Result<{ deployment: DeploymentRow }>> {
  return guarded((op) => modelsBackend.addPrice(uuid, body, op), PRICE_ERRORS);
}

export async function retireAction(
  uuid: string,
  body: { retire_after: string; reason: string },
): Promise<Result<{ deployment: DeploymentRow; proposals: ProposalOut[] }>> {
  return guarded((op) => modelsBackend.retire(uuid, body, op));
}

export async function unavailableAction(uuid: string, reason: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.unavailable(uuid, reason, op));
}

export async function cancelRetirementAction(uuid: string, reason: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.cancelRetirement(uuid, reason, op));
}

export async function restoreAction(uuid: string, reason: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.restore(uuid, reason, op));
}

export async function putWeightsAction(uuid: string, body: WeightsIn): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.putWeights(uuid, body, op));
}

export async function putSalePolicyAction(
  body: SalePolicyIn,
): Promise<Result<{ sale_policy: SalePolicy; applied_to: string[] }>> {
  return guarded((op) => modelsBackend.putSalePolicy(body, op), POLICY_ERRORS);
}

/** Spec 065 (`contracts/api.md`): the model can answer the agents in this environment. */
export async function respondEnableAction(uuid: string, note: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.respondEnable(uuid, note, op));
}

/** Spec 065: it stops being choosable; a model in use is refused in words (`model_in_use`). */
export async function respondDisableAction(uuid: string, reason: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.respondDisable(uuid, reason, op));
}

/**
 * The API asks for a reason even without `confirm`, and stores nothing then: the
 * reason that goes to the audit is the one of the confirmation.
 */
const PREVIEW_REASON = "Revisar los agentes que cambian, sin guardar";

/**
 * Spec 065 (13.2): which agents would change with the default. Without `confirm`
 * the API answers `409 confirm_required` with them: that is the answer here, not
 * a failure. Nothing changes.
 */
export async function previewRespondDefaultAction(
  modelId: string,
): Promise<Result<{ affected: RespondDefaultAffected[] }>> {
  const operator = await requireOperator();
  try {
    await modelsBackend.putRespondDefault({ model_id: modelId, reason: PREVIEW_REASON, confirm: false }, operator.id);
    // An API that saved without `confirm` is not this contract: say what it did.
    revalidatePath("/models");
    return { ok: false, error: "La API cambió el modelo por defecto sin pedir confirmación. Revisa cuál quedó." };
  } catch (err) {
    const detail = detailOf(err);
    if (detail?.code === "confirm_required" && Array.isArray(detail.affected)) {
      return { ok: true, data: { affected: detail.affected as RespondDefaultAffected[] } };
    }
    return refusal(err, ERRORS);
  }
}

/** Spec 065 (13.2–13.5): the change, confirmed, with its reason. Silent for the partners (13.6). */
export async function confirmRespondDefaultAction(modelId: string, reason: string): Promise<Result<RespondDefault>> {
  return guarded((op) => modelsBackend.putRespondDefault({ model_id: modelId, reason, confirm: true }, op));
}
