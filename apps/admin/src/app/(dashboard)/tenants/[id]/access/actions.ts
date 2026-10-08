"use server";

import { revalidatePath } from "next/cache";

import { backend, BackendError, type ClientAccessOut, type ClientInvitationOut, type ClientModule } from "@/lib/backend";
import { requireOperator } from "@/lib/session";

import { ACCESS_ERRORS } from "./messages";

/**
 * Spec 030: the client-access tab. Every call carries the operator of the
 * panel session (`X-Operator-Id`): the API audits a person, not the token.
 */
type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function toError(err: unknown): string {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? (err.body as { detail: unknown }).detail
        : null;
    if (detail && typeof detail === "object" && "code" in detail) {
      const code = String((detail as { code: unknown }).code);
      return ACCESS_ERRORS[code] ?? code;
    }
    if (typeof detail === "string") return detail;
    return `Error ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}

async function guarded<T>(tenantId: string, fn: (operatorId: string) => Promise<T | null>): Promise<Result<T>> {
  const operator = await requireOperator();
  try {
    const data = await fn(operator.id);
    revalidatePath(`/tenants/${tenantId}/access`);
    return { ok: true, data: data as T };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function setAccessAction(
  tenantId: string,
  body: { enabled: boolean; modules: ClientModule[] },
): Promise<Result<ClientAccessOut>> {
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
