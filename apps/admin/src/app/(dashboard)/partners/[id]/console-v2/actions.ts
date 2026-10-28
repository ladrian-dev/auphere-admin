"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import { leversBackend, type ConsoleV2State, type DryRunResult } from "@/lib/backend-levers";
import { requireOperator } from "@/lib/session";

import { CONSOLE_V2_ERRORS } from "./console-v2";

const path = (partnerId: string) => `/partners/${partnerId}/console-v2`;

/** Spec 047 (55.4): the dry run, with an optional reason. It changes nothing and leaves its report. */
export async function consoleV2DryRunAction(partnerId: string, reason: string | null): Promise<Result<DryRunResult>> {
  const operator = await requireOperator();
  try {
    const data = await leversBackend.consoleV2DryRun(partnerId, reason, operator.id);
    revalidatePath(path(partnerId));
    return { ok: true, data: data as DryRunResult };
  } catch (err) {
    return toFailure(err, CONSOLE_V2_ERRORS);
  }
}

/** Spec 047 (55.2, 55.4): turn the new console on, with a clean dry run of the last 24 h and a reason. */
export async function consoleV2EnableAction(partnerId: string, reason: string): Promise<Result<ConsoleV2State>> {
  const operator = await requireOperator();
  try {
    const data = await leversBackend.consoleV2Enable(partnerId, reason, operator.id);
    revalidatePath(path(partnerId));
    return { ok: true, data: data as ConsoleV2State };
  } catch (err) {
    return toFailure(err, CONSOLE_V2_ERRORS);
  }
}

/** Spec 047 (55.5): back to today's console, with a reason, until the partner confirms the split in bags. */
export async function consoleV2DisableAction(partnerId: string, reason: string): Promise<Result<ConsoleV2State>> {
  const operator = await requireOperator();
  try {
    const data = await leversBackend.consoleV2Disable(partnerId, reason, operator.id);
    revalidatePath(path(partnerId));
    return { ok: true, data: data as ConsoleV2State };
  } catch (err) {
    return toFailure(err, CONSOLE_V2_ERRORS);
  }
}
