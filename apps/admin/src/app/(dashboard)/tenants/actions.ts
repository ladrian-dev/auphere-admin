"use server";

/**
 * Block M.1 — tenant lifecycle server actions.
 *
 * Pause / Resume / Archive go through ``PUT /admin/tenants/:id`` with the
 * partial body the existing endpoint accepts. Delete uses the new
 * ``DELETE /admin/tenants/:id`` which 409s unless the tenant is already
 * archived — the two-step is intentional safety.
 *
 * All actions revalidate ``/tenants`` and the per-tenant root. Toasts on
 * the client side surface errors verbatim from the backend so the
 * operator sees the real reason instead of a generic message.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend, type TenantStatus } from "@/lib/backend";

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

function err(e: unknown): { ok: false; error: string } {
  if (e instanceof BackendError) {
    const body = e.body as { detail?: string } | null;
    return { ok: false, error: body?.detail ?? `HTTP ${e.status}` };
  }
  return { ok: false, error: e instanceof Error ? e.message : String(e) };
}

export async function setTenantStatusAction(
  tenantId: string,
  status: TenantStatus,
): Promise<ActionResult<{ status: TenantStatus }>> {
  try {
    const r = await backend.updateTenant(tenantId, { status });
    if (!r) return { ok: false, error: "empty response" };
    revalidatePath("/tenants");
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { status: r.status } };
  } catch (e) {
    return err(e);
  }
}

/**
 * Hard delete a tenant. The backend requires status='archived' first;
 * we surface its 409 verbatim if the caller skips that step. The caller
 * MUST have shown a confirm dialog where the operator typed the slug
 * back to us — the typing is the UX speedbump, not a server check (the
 * tenant could be renamed between dialog open and submit).
 *
 * Caller decides navigation: from the table row, stay on /tenants and
 * let revalidate drop the row; from the per-tenant page, push to
 * /tenants on success.
 */
export async function deleteTenantAction(
  tenantId: string,
): Promise<ActionResult<{ deleted: true }>> {
  try {
    await backend.deleteTenant(tenantId);
    revalidatePath("/tenants");
    return { ok: true, data: { deleted: true } };
  } catch (e) {
    return err(e);
  }
}
