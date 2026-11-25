"use server";

/**
 * Spec 077 (requisito 5): the client's sending keys. Every write names the
 * operator (`X-Operator-Id`) and lands in the audit with their name.
 */

import { revalidatePath } from "next/cache";

import { toCodedFailure, type Result } from "@/lib/action-result";
import { backend, type TenantApiKeyCreatedOut, type TenantApiKeyOut } from "@/lib/backend";
import { SEND_ONLY_ERRORS } from "@/lib/send-only";
import { requireOperator } from "@/lib/session";

function revalidate(tenantId: string) {
  revalidatePath(`/tenants/${tenantId}/api`);
  // The «Puesta en marcha» of the Resumen counts the active keys.
  revalidatePath(`/tenants/${tenantId}`);
}

export async function createTenantKeyAction(tenantId: string): Promise<Result<TenantApiKeyCreatedOut>> {
  const operator = await requireOperator("credentials");
  try {
    const data = await backend.createTenantApiKey(tenantId, operator.id);
    if (!data?.plaintext) return { ok: false, error: "La API no devolvió la clave." };
    revalidate(tenantId);
    return { ok: true, data };
  } catch (err) {
    return toCodedFailure(err, SEND_ONLY_ERRORS);
  }
}

export async function rotateTenantKeyAction(
  tenantId: string,
  keyId: string,
  graceHours: number,
): Promise<Result<TenantApiKeyCreatedOut>> {
  const operator = await requireOperator("credentials");
  if (!Number.isInteger(graceHours) || graceHours < 0 || graceHours > 336) {
    return { ok: false, error: "Las horas de gracia van de 0 a 336." };
  }
  try {
    const data = await backend.rotateTenantApiKey(tenantId, keyId, graceHours, operator.id);
    if (!data?.plaintext) return { ok: false, error: "La API no devolvió la clave nueva." };
    revalidate(tenantId);
    return { ok: true, data };
  } catch (err) {
    return toCodedFailure(err, SEND_ONLY_ERRORS);
  }
}

export async function revokeTenantKeyAction(tenantId: string, keyId: string): Promise<Result<TenantApiKeyOut | null>> {
  const operator = await requireOperator("credentials");
  try {
    const data = await backend.revokeTenantApiKey(tenantId, keyId, operator.id);
    revalidate(tenantId);
    return { ok: true, data };
  } catch (err) {
    return toCodedFailure(err, SEND_ONLY_ERRORS);
  }
}
