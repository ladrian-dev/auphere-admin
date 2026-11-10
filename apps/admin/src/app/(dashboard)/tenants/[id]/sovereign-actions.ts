"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import { leversBackend, type SovereignState } from "@/lib/backend-levers";
import { requireOperator } from "@/lib/session";

import { SOVEREIGN_ERRORS } from "./sovereign";

/** Spec 047 (T172, 54.6): turn the client's sovereign restriction on or off, with a reason. */
export async function setSovereignAction(
  tenantId: string,
  body: { enabled: boolean; reason: string },
): Promise<Result<SovereignState>> {
  const operator = await requireOperator();
  try {
    const data = await leversBackend.setSovereign(tenantId, body, operator.id);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: data as SovereignState };
  } catch (err) {
    return toFailure(err, SOVEREIGN_ERRORS);
  }
}
