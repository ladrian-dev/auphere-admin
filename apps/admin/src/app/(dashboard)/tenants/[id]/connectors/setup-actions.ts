"use server";

/**
 * Server actions for the non-OAuth connector wizards (manual setup).
 *
 * Each action chains the legacy provider-specific endpoint with a call
 * to the unified ``bootstrap-*`` endpoint of the connectors module so
 * the operator ends up with a ``tenant_connector`` row visible in the
 * "Conectados" section after a successful run.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend } from "@/lib/backend";
import type { WhatsAppPreview } from "@/lib/backend";
import { requireSession } from "@/lib/session";

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

function toError(err: unknown): string {
  if (err instanceof BackendError) {
    const body = err.body as { detail?: string } | null;
    return body?.detail ?? `HTTP ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}

// ── WhatsApp YCloud ────────────────────────────────────────────────────────

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

export async function connectWhatsAppSetupAction(
  tenantId: string,
  body: { waba_id: string; phone_number_id: string },
): Promise<ActionResult<{ phone_number: string }>> {
  await requireSession();
  try {
    const channel = await backend.connectWhatsAppManual(tenantId, body);
    if (!channel) {
      return { ok: false, error: "El backend no devolvió el canal creado." };
    }
    // Install the connector row so the channel shows up under "Conectados".
    await backend.connectManualConnector(tenantId, "whatsapp_ycloud", {
      channel_id: channel.channel_id,
    });
    revalidatePath(`/tenants/${tenantId}/connectors`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { phone_number: channel.phone_number } };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

// ── AgendaPro browser_credentials ──────────────────────────────────────────

export async function agendaProSetupAction(
  tenantId: string,
  body: { login: string; password: string; business_url?: string | null },
): Promise<ActionResult<{ context_id: string }>> {
  await requireSession();
  try {
    const bootstrap = await backend.bootstrapAgendaPro(tenantId, body);
    if (!bootstrap) {
      return { ok: false, error: "Bootstrap no retornó datos." };
    }
    await backend.bootstrapBrowserConnector(tenantId, "agendapro", {
      tenant_credentials_id: bootstrap.tenant_credentials_id,
      context_id: bootstrap.context_id,
    });
    revalidatePath(`/tenants/${tenantId}/connectors`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { context_id: bootstrap.context_id } };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function agendaProHealthCheckAction(
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
    revalidatePath(`/tenants/${tenantId}/connectors`);
    if (!result) {
      return { ok: false, error: "Health check no retornó datos." };
    }
    return {
      ok: true,
      data: {
        healthy: result.healthy,
        needs_reauth: result.needs_reauth,
        notes: result.notes,
      },
    };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
