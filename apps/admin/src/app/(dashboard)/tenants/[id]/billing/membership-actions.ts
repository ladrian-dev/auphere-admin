"use server";

/**
 * Spec 077 (requisitos 6, 7 y 8): the client's membership. Every write names
 * the operator (`X-Operator-Id`) and lands in the audit with their name.
 */

import { revalidatePath } from "next/cache";

import { toCodedFailure, type Result } from "@/lib/action-result";
import { backend, type MembershipCheckoutOut, type MembershipOut, type MembershipPutInput } from "@/lib/backend";
import { SEND_ONLY_ERRORS } from "@/lib/send-only";
import { requireOperator } from "@/lib/session";

function revalidate(tenantId: string) {
  revalidatePath(`/tenants/${tenantId}/billing`);
  // The header pill and the «Puesta en marcha» read the membership too.
  revalidatePath(`/tenants/${tenantId}`, "layout");
}

async function run<T>(tenantId: string, fn: (operatorId: string) => Promise<T | null>): Promise<Result<T | null>> {
  const operator = await requireOperator();
  try {
    const data = await fn(operator.id);
    revalidate(tenantId);
    return { ok: true, data };
  } catch (err) {
    return toCodedFailure(err, SEND_ONLY_ERRORS);
  }
}

export async function putMembershipAction(
  tenantId: string,
  body: MembershipPutInput,
): Promise<Result<MembershipOut | null>> {
  // Spec 078: the guard goes first, before even validating the input.
  await requireOperator();
  if (!Number.isInteger(body.amount_cents) || body.amount_cents <= 0) {
    return { ok: false, error: SEND_ONLY_ERRORS.invalid_amount };
  }
  return run(tenantId, (op) => backend.putMembership(tenantId, body, op));
}

/** 204 on success: there is nothing to return. */
export async function archiveMembershipAction(tenantId: string): Promise<Result<null>> {
  const res = await run(tenantId, (op) => backend.archiveMembership(tenantId, op));
  return res.ok ? { ok: true, data: null } : res;
}

export async function membershipCheckoutAction(tenantId: string): Promise<Result<MembershipCheckoutOut | null>> {
  return run(tenantId, (op) => backend.membershipCheckout(tenantId, op));
}

export async function refreshMembershipAction(tenantId: string): Promise<Result<MembershipOut | null>> {
  return run(tenantId, (op) => backend.refreshMembership(tenantId, op));
}

export async function chargeMembershipAction(tenantId: string): Promise<Result<MembershipOut | null>> {
  return run(tenantId, (op) => backend.chargeMembership(tenantId, op));
}

export async function cancelMembershipAction(tenantId: string): Promise<Result<MembershipOut | null>> {
  return run(tenantId, (op) => backend.cancelMembership(tenantId, op));
}
