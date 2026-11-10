"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import {
  modelsBackend,
  type ProfilePolicyJson,
  type RouterPreview,
  type RouterProfile,
} from "@/lib/backend-models";
import { requireOperator } from "@/lib/session";

import { ERRORS } from "./policy";

/**
 * Spec 047 (T150): a new version of a profile, with who and why (40.13); and
 * the preview, which decides without calling any model.
 */
export async function saveProfileAction(
  profile: string,
  body: { policy: ProfilePolicyJson; reason: string },
): Promise<Result<RouterProfile>> {
  const operator = await requireOperator();
  try {
    const data = await modelsBackend.saveProfile(profile, body, operator.id);
    revalidatePath("/router");
    return { ok: true, data: data as RouterProfile };
  } catch (err) {
    return toFailure(err, ERRORS);
  }
}

export async function previewAction(body: {
  tenant_id: string;
  agent_id?: string;
  task: string;
  profile?: string;
}): Promise<Result<RouterPreview>> {
  await requireOperator();
  try {
    const data = await modelsBackend.preview(body);
    return { ok: true, data: data as RouterPreview };
  } catch (err) {
    return toFailure(err, ERRORS);
  }
}
