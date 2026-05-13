"use server";

/**
 * Block P — server actions for the eval suite.
 *
 * Mutations revalidate the agent page so the Recent Runs list refreshes
 * after creating a dataset / case / run. The run action is special: it
 * blocks until the run finishes (10-60s typical) so the client can show
 * the result inline.
 */

import { revalidatePath } from "next/cache";

import {
  backend,
  BackendError,
  type EvalCase,
  type EvalCaseAssertions,
  type EvalDataset,
  type EvalRunDetail,
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
  return err instanceof Error ? err.message : String(err);
}

export async function createDatasetAction(
  tenantId: string,
  body: { name: string; description?: string | null },
): Promise<Result<EvalDataset>> {
  await requireSession();
  try {
    const r = await backend.createEvalDataset(tenantId, body);
    revalidatePath(`/tenants/${tenantId}/agent`);
    return { ok: true, data: r! };
  } catch (e) {
    return { ok: false, error: pluck(e) };
  }
}

export async function createCaseAction(
  tenantId: string,
  datasetId: string,
  body: {
    name: string;
    user_message: string;
    assertions: EvalCaseAssertions;
  },
): Promise<Result<EvalCase>> {
  await requireSession();
  try {
    const r = await backend.createEvalCase(tenantId, datasetId, body);
    revalidatePath(`/tenants/${tenantId}/agent`);
    return { ok: true, data: r! };
  } catch (e) {
    return { ok: false, error: pluck(e) };
  }
}

export async function deleteCaseAction(
  tenantId: string,
  caseId: string,
): Promise<Result<null>> {
  await requireSession();
  try {
    await backend.deleteEvalCase(tenantId, caseId);
    revalidatePath(`/tenants/${tenantId}/agent`);
    return { ok: true, data: null };
  } catch (e) {
    return { ok: false, error: pluck(e) };
  }
}

export async function triggerRunAction(
  tenantId: string,
  datasetId: string,
  body: { agent_config_version?: number },
): Promise<Result<EvalRunDetail>> {
  await requireSession();
  try {
    const r = await backend.triggerEvalRun(tenantId, datasetId, body);
    revalidatePath(`/tenants/${tenantId}/agent`);
    return { ok: true, data: r! };
  } catch (e) {
    return { ok: false, error: pluck(e) };
  }
}
