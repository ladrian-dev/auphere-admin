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

// AgendaPro legacy admin/credentials actions were removed in migration
// 0021 (ADR-017). Use ``agendaProSetPublicUrlAction`` in
// ``connectors/setup-actions.ts`` to configure the tenant's public
// AgendaPro URL instead.

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
