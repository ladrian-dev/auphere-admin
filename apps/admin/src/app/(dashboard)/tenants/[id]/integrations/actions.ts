"use server";

import { revalidatePath } from "next/cache";

import { backend, BackendError } from "@/lib/backend";
import type { WhatsAppConnect, WhatsAppPreview } from "@/lib/backend";
import { requireSession } from "@/lib/session";

type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

function toError(err: unknown): string {
  if (err instanceof BackendError) {
    if (typeof err.body === "object" && err.body && "detail" in err.body) {
      return String((err.body as { detail: unknown }).detail);
    }
    return `error ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}

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
    return { ok: false, error: toError(err) };
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
    return { ok: false, error: toError(err) };
  }
}

// ── WhatsApp manual setup (Block J) ────────────────────────────────────────

export async function verifyWhatsAppAction(
  waba_id: string,
  phone_number_id: string,
): Promise<ActionResult<WhatsAppPreview>> {
  await requireSession();
  try {
    const result = await backend.verifyWhatsApp(waba_id, phone_number_id);
    if (!result) {
      return { ok: false, error: "El backend no devolvió datos del número." };
    }
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function connectWhatsAppManualAction(
  tenantId: string,
  body: { waba_id: string; phone_number_id: string },
): Promise<ActionResult<WhatsAppConnect>> {
  await requireSession();
  try {
    const result = await backend.connectWhatsAppManual(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió el canal creado." };
    }
    revalidatePath(`/tenants/${tenantId}/integrations`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
