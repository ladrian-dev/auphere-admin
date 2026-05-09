"use server";

import { redirect } from "next/navigation";

import { backend, BackendError } from "@/lib/backend";
import type { TenantCreateInput } from "@/lib/backend";

export type CreateTenantState =
  | { kind: "error"; message: string }
  | { kind: "ok"; tenantId: string };

export async function createTenantAction(
  input: TenantCreateInput,
): Promise<CreateTenantState> {
  try {
    const tenant = await backend.createTenant(input);
    if (!tenant) {
      return { kind: "error", message: "El backend no devolvió el tenant creado." };
    }
    // Redirect happens client-side after the success state propagates so the
    // form can show a toast first. The new tenant id is returned to the form.
    return { kind: "ok", tenantId: tenant.id };
  } catch (err) {
    if (err instanceof BackendError) {
      const detail =
        typeof err.body === "object" && err.body !== null && "detail" in err.body
          ? String((err.body as { detail: unknown }).detail)
          : err.message;
      return { kind: "error", message: detail };
    }
    return {
      kind: "error",
      message: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function checkSlugAction(slug: string): Promise<{ available: boolean }> {
  try {
    const result = await backend.checkSlugAvailability(slug);
    return { available: result?.available ?? false };
  } catch {
    // If the network probe fails, fall back to permissive (the POST will
    // 409 if there's a real conflict). Don't block the form.
    return { available: true };
  }
}

export async function gotoTenantIntegrations(tenantId: string): Promise<never> {
  redirect(`/tenants/${tenantId}/integrations`);
}
