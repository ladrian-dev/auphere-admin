"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import {
  modelsBackend,
  type DeploymentIn,
  type DeploymentRow,
  type PriceIn,
  type ProposalOut,
} from "@/lib/backend-models";
import { requireOperator } from "@/lib/session";

import { ERRORS } from "./labels";

/**
 * Spec 047 (T150): the catalog's writes. Each one carries the operator of the
 * panel session and its reason; the API audits both and the change applies
 * from the next turn.
 */
async function guarded<T>(fn: (operatorId: string) => Promise<T | null>): Promise<Result<T>> {
  const operator = await requireOperator();
  try {
    const data = await fn(operator.id);
    revalidatePath("/models");
    return { ok: true, data: data as T };
  } catch (err) {
    return toFailure(err, ERRORS);
  }
}

export async function createDeploymentAction(body: DeploymentIn): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.createDeployment(body, op));
}

export async function activateAction(uuid: string, reason: string): Promise<Result<DeploymentRow>> {
  return guarded((op) => modelsBackend.activate(uuid, reason, op));
}

export async function addPriceAction(
  uuid: string,
  body: PriceIn,
): Promise<Result<{ alerts: number; deployment: DeploymentRow }>> {
  return guarded((op) => modelsBackend.addPrice(uuid, body, op));
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
