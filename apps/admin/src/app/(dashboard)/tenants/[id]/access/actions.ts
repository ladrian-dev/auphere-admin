"use server";

import { revalidatePath } from "next/cache";

import {
  backend,
  BackendError,
  type ClientAccessIn,
  type ClientAccessOut,
  type ClientInvitationOut,
  type ClientPhoneOut,
} from "@/lib/backend";
import { requireOperator } from "@/lib/session";

import { ACCESS_ERRORS, PHONE_GONE } from "./messages";

/**
 * Spec 030: the client-access tab. Every call carries the operator of the
 * panel session (`X-Operator-Id`): the API audits a person, not the token.
 *
 * Spec 043: a refusal keeps its `code` (and `count`, for `live_reservations`)
 * so the form can offer a choice instead of only showing a sentence.
 */
type Failure = { ok: false; error: string; code?: string; count?: number };
type Result<T> = { ok: true; data: T } | Failure;

function toFailure(err: unknown): Failure {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? (err.body as { detail: unknown }).detail
        : null;
    if (detail && typeof detail === "object" && "code" in detail) {
      const code = String((detail as { code: unknown }).code);
      const count = "count" in detail ? (detail as { count: unknown }).count : undefined;
      return {
        ok: false,
        error: ACCESS_ERRORS[code] ?? code,
        code,
        ...(typeof count === "number" ? { count } : {}),
      };
    }
    if (typeof detail === "string") return { ok: false, error: detail };
    return { ok: false, error: `Error ${err.status}` };
  }
  return { ok: false, error: err instanceof Error ? err.message : String(err) };
}

async function guarded<T>(tenantId: string, fn: (operatorId: string) => Promise<T | null>): Promise<Result<T>> {
  const operator = await requireOperator();
  try {
    const data = await fn(operator.id);
    revalidatePath(`/tenants/${tenantId}/access`);
    return { ok: true, data: data as T };
  } catch (err) {
    return toFailure(err);
  }
}

export async function setAccessAction(tenantId: string, body: ClientAccessIn): Promise<Result<ClientAccessOut>> {
  return guarded(tenantId, (op) => backend.setClientAccess(tenantId, body, op));
}

export async function inviteAction(
  tenantId: string,
  body: { email: string; name?: string | null },
): Promise<Result<ClientInvitationOut>> {
  return guarded(tenantId, (op) => backend.inviteClientMember(tenantId, body, op));
}

export async function resendAction(tenantId: string, memberId: string): Promise<Result<ClientInvitationOut>> {
  return guarded(tenantId, (op) => backend.resendClientInvitation(tenantId, memberId, op));
}

export async function revokeAction(tenantId: string, memberId: string): Promise<Result<null>> {
  return guarded(tenantId, (op) => backend.revokeClientMember(tenantId, memberId, op));
}

/** Spec 031 (R7.4): the phones of one person. A read: nothing to revalidate. */
export async function listPhonesAction(tenantId: string, memberId: string): Promise<Result<ClientPhoneOut[]>> {
  const operator = await requireOperator();
  try {
    return { ok: true, data: (await backend.listClientMemberPhones(tenantId, memberId, operator.id)) ?? [] };
  } catch (err) {
    return toFailure(err);
  }
}

/** Spec 031 (R7.4): Auphere closes one phone (a lost one, say). Audited with this operator. */
export async function closePhoneAction(tenantId: string, memberId: string, phoneId: string): Promise<Result<null>> {
  const operator = await requireOperator();
  try {
    await backend.closeClientMemberPhone(tenantId, memberId, phoneId, operator.id);
    return { ok: true, data: null };
  } catch (err) {
    if (err instanceof BackendError && err.status === 404) return { ok: false, error: PHONE_GONE };
    return toFailure(err);
  }
}
