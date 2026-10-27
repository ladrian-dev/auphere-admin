"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import { modelsBackend } from "@/lib/backend-models";
import { requireOperator } from "@/lib/session";

import { RUN_ERRORS } from "./labels";

/** Spec 047 (T150, 42.6): a certification launched by Auphere, outside the partner's lines. */
export async function launchCertificationAction(body: {
  deployment_id: string;
  tasks?: string[];
  agent_ids?: string[];
}): Promise<Result<{ jobs: { job_id: string }[] }>> {
  const operator = await requireOperator();
  try {
    const data = await modelsBackend.launchCertification(body, operator.id);
    revalidatePath("/certifications");
    return { ok: true, data: data as { jobs: { job_id: string }[] } };
  } catch (err) {
    return toFailure(err, RUN_ERRORS);
  }
}
