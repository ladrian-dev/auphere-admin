"use server";

import { revalidatePath } from "next/cache";

import { backend, BackendError } from "@/lib/backend";
import type {
  BackchannelOwnerCreateInput,
  BackchannelOwnerUpdateInput,
  OwnerPhoneIndexOut,
} from "@/lib/backend";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

function _toError(err: unknown): string {
  if (err instanceof BackendError) {
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? String((err.body as { detail: unknown }).detail)
        : err.message;
    return detail;
  }
  return err instanceof Error ? err.message : String(err);
}

/**
 * Register a new owner phone for this tenant. Wraps the backend call
 * + revalidates the tab so the table refreshes immediately.
 */
export async function registerOwnerAction(
  tenantId: string,
  body: BackchannelOwnerCreateInput,
): Promise<Result<OwnerPhoneIndexOut>> {
  try {
    const row = await backend.registerBackchannelOwner(tenantId, body);
    revalidatePath(`/tenants/${tenantId}/backchannel`);
    if (!row) return { ok: false, error: "Backend returned null" };
    return { ok: true, data: row };
  } catch (err) {
    return { ok: false, error: _toError(err) };
  }
}

export async function updateOwnerAction(
  tenantId: string,
  phoneE164: string,
  body: BackchannelOwnerUpdateInput,
): Promise<Result<OwnerPhoneIndexOut>> {
  try {
    const row = await backend.updateBackchannelOwner(tenantId, phoneE164, body);
    revalidatePath(`/tenants/${tenantId}/backchannel`);
    if (!row) return { ok: false, error: "Backend returned null" };
    return { ok: true, data: row };
  } catch (err) {
    return { ok: false, error: _toError(err) };
  }
}

export async function deregisterOwnerAction(
  tenantId: string,
  phoneE164: string,
): Promise<Result<null>> {
  try {
    await backend.deregisterBackchannelOwner(tenantId, phoneE164);
    revalidatePath(`/tenants/${tenantId}/backchannel`);
    return { ok: true, data: null };
  } catch (err) {
    return { ok: false, error: _toError(err) };
  }
}
