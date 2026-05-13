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

// ── AgendaPro public link (ADR-017) ────────────────────────────────────────

/**
 * Save the tenant's public AgendaPro URL. The new public browser MCP
 * (future session) reads this column to scrape availability and create
 * appointments via the public booking link. Cancel / modify / list
 * appointments are out of scope for the public flow and the agent
 * escalates them to the owner via the backchannel (ADR-018).
 *
 * Pass an empty string (or null) to clear the URL.
 */
export async function agendaProSetPublicUrlAction(
  tenantId: string,
  publicUrl: string | null,
): Promise<ActionResult<{ public_url: string | null }>> {
  await requireSession();
  try {
    const result = await backend.setAgendaProPublicUrl(tenantId, publicUrl);
    if (!result) {
      return { ok: false, error: "El backend no retornó datos." };
    }
    revalidatePath(`/tenants/${tenantId}/connectors`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { public_url: result.public_url } };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
