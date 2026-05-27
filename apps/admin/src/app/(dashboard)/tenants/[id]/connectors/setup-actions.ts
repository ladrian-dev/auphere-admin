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
import type {
  MetaSignupInput,
  MetaSignupResult,
  MetaTestSendInput,
  MetaTestSendResult,
  WhatsAppPreview,
} from "@/lib/backend";
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
  phone_number_e164: string,
): Promise<ActionResult<WhatsAppPreview>> {
  await requireSession();
  try {
    const result = await backend.verifyWhatsApp(waba_id, phone_number_e164);
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
  body: { waba_id: string; phone_number_e164: string },
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

// ── WhatsApp Meta (Embedded Signup v4) ─────────────────────────────────────

/**
 * Complete a Meta Embedded Signup flow.
 *
 * The browser dialog already ran ``FB.login`` with the appropriate
 * ``config_id`` and captured the OAuth ``code`` plus the ``data`` envelope
 * (``waba_id`` / ``phone_number_id`` / ``business_id``). This server action:
 *
 * 1. Hands everything to the backend orchestrator (exchange → register →
 *    subscribe → persist credentials → upsert channels row).
 * 2. Installs the ``whatsapp_meta`` connector row pointing at the freshly
 *    created channel so the panel's "Conectados" section reflects it.
 * 3. Revalidates the connectors + tenant pages so the UI updates without
 *    a hard refresh.
 *
 * The action NEVER receives or surfaces the BISUAT — the orchestrator
 * encrypts and persists it, and the response carries only public metadata.
 */
export async function connectMetaWhatsAppSetupAction(
  tenantId: string,
  body: MetaSignupInput,
): Promise<ActionResult<MetaSignupResult>> {
  await requireSession();
  try {
    const result = await backend.metaSignup(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió datos del signup." };
    }
    await backend.connectManualConnector(tenantId, "whatsapp_meta", {
      channel_id: result.channel_id,
    });
    revalidatePath(`/tenants/${tenantId}/connectors`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

/**
 * Send a one-off test message from the tenant's connected Meta WhatsApp
 * channel. Used by the "Enviar prueba" button to smoke-test the BISUAT
 * and to exercise whatsapp_business_messaging for App Review evidence.
 */
export async function metaTestSendAction(
  tenantId: string,
  body: MetaTestSendInput,
): Promise<ActionResult<MetaTestSendResult>> {
  await requireSession();
  try {
    const result = await backend.metaTestSend(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió wamid." };
    }
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

// ── WooCommerce (api_key, ADR-019) ─────────────────────────────────────────

/**
 * Connect a tenant's WooCommerce store. The operator pasted store URL
 * + Consumer Key + Consumer Secret in the wizard; we POST them to the
 * api_key bootstrap endpoint which Fernet-encrypts the credentials in
 * tenant_credentials and creates the tenant_connectors install row.
 */
export async function connectWooCommerceSetupAction(
  tenantId: string,
  body: {
    store_url: string;
    consumer_key: string;
    consumer_secret: string;
  },
): Promise<ActionResult<{ store_url: string }>> {
  await requireSession();
  try {
    const storeUrl = body.store_url.trim().replace(/\/+$/, "");
    if (!storeUrl.startsWith("https://")) {
      return {
        ok: false,
        error: "La URL de la tienda debe empezar con https://",
      };
    }
    await backend.connectApiKeyConnector(tenantId, "woocommerce", {
      secrets: {
        consumer_key: body.consumer_key.trim(),
        consumer_secret: body.consumer_secret.trim(),
      },
      endpoint_meta: { store_url: storeUrl },
    });
    revalidatePath(`/tenants/${tenantId}/connectors`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { store_url: storeUrl } };
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
