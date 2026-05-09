"use server";

import { revalidatePath } from "next/cache";

import { backend, BackendError } from "@/lib/backend";
import { requireSession } from "@/lib/session";

type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

export async function bootstrapAgendaProAction(
  tenantId: string,
  body: { login: string; password: string; business_url?: string | null },
): Promise<ActionResult<{ context_id: string; audit_log_id: string }>> {
  await requireSession();
  try {
    const result = await backend.bootstrapAgendaPro(tenantId, body);
    revalidatePath(`/tenants/${tenantId}/integrations`);
    revalidatePath(`/tenants/${tenantId}`);
    return {
      ok: true,
      data: { context_id: result!.context_id, audit_log_id: result!.audit_log_id },
    };
  } catch (err) {
    return {
      ok: false,
      error:
        err instanceof BackendError
          ? typeof err.body === "object" && err.body && "detail" in err.body
            ? String((err.body as { detail: unknown }).detail)
            : `error ${err.status}`
          : err instanceof Error
            ? err.message
            : String(err),
    };
  }
}

export async function healthCheckAgendaProAction(
  tenantId: string,
): Promise<
  ActionResult<{
    healthy: boolean;
    needs_reauth: boolean;
    notes: string | null;
  }>
> {
  await requireSession();
  try {
    const result = await backend.healthCheckAgendaPro(tenantId);
    revalidatePath(`/tenants/${tenantId}/integrations`);
    revalidatePath(`/tenants/${tenantId}`);
    return {
      ok: true,
      data: {
        healthy: result!.healthy,
        needs_reauth: result!.needs_reauth,
        notes: result!.notes,
      },
    };
  } catch (err) {
    return {
      ok: false,
      error:
        err instanceof BackendError
          ? typeof err.body === "object" && err.body && "detail" in err.body
            ? String((err.body as { detail: unknown }).detail)
            : `error ${err.status}`
          : err instanceof Error
            ? err.message
            : String(err),
    };
  }
}
