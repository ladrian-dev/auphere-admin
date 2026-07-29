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
  MetaConnectOwnedInput,
  MetaSignupInput,
  MetaSignupResult,
  MetaTestSendInput,
  MetaTestSendResult,
  WhatsAppTemplateCreateInput,
  WhatsAppTemplateCreateResult,
  WhatsAppTemplateList,
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
 * Connect a WhatsApp number the app OWNER already controls (a number under
 * the portfolio that owns the Auphere app — Facelad), via a permanent
 * System User token. Embedded Signup refuses that portfolio, so this is
 * the manual path: the backend skips the OAuth exchange, subscribes the
 * webhook, persists the token, upserts the channel and stores catalog_id.
 * Then installs the whatsapp_meta connector row like the signup action.
 *
 * The System User token is a secret: it is POSTed straight to the backend
 * (which Fernet-encrypts it) and never stored client-side or surfaced back.
 */
export async function connectMetaOwnedNumberAction(
  tenantId: string,
  body: MetaConnectOwnedInput,
): Promise<ActionResult<MetaSignupResult>> {
  await requireSession();
  try {
    const result = await backend.metaConnectOwned(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió datos de la conexión." };
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

// ── TikTok Business Messaging (OAuth redirect) ─────────────────────────────

/**
 * Mint the URL the business owner opens to authorise the Auphere TikTok app.
 *
 * Deliberately different from the Meta flow: TikTok uses a server-side
 * redirect, so the panel never sees the ``auth_code``. The owner leaves for
 * TikTok, TikTok posts the code straight to the API callback, and the
 * callback bounces the browser back here with ``?tiktok=<status>``. That is
 * why this action returns a URL rather than a connected channel — and why
 * the connector row is installed by the callback, not by the panel.
 */
export async function tiktokAuthorizeUrlAction(
  tenantId: string,
): Promise<ActionResult<{ authorize_url: string }>> {
  await requireSession();
  try {
    const result = await backend.tiktokAuthorizeUrl(tenantId);
    if (!result) {
      return { ok: false, error: "El backend no devolvió la URL de autorización." };
    }
    return { ok: true, data: { authorize_url: result.authorize_url } };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

/**
 * Offboard the tenant from TikTok. Deletes the webhook registration on
 * TikTok's side first so they stop delivering to a channel we no longer
 * serve, then drops the credentials and marks the channel disconnected.
 */
export async function tiktokDisconnectAction(
  tenantId: string,
): Promise<ActionResult<{ status: string }>> {
  await requireSession();
  try {
    const result = await backend.tiktokDisconnect(tenantId);
    if (!result) {
      return { ok: false, error: "El backend no confirmó la desconexión." };
    }
    revalidatePath(`/tenants/${tenantId}/connectors`);
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { status: result.status } };
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

// ── WhatsApp template (HSM) management ─────────────────────────────────────

export async function listWhatsAppTemplatesAction(
  tenantId: string,
): Promise<ActionResult<WhatsAppTemplateList>> {
  await requireSession();
  try {
    const result = await backend.listWhatsAppTemplates(tenantId);
    if (!result) {
      return { ok: false, error: "El backend no devolvió plantillas." };
    }
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function createWhatsAppTemplateAction(
  tenantId: string,
  body: WhatsAppTemplateCreateInput,
): Promise<ActionResult<WhatsAppTemplateCreateResult>> {
  await requireSession();
  try {
    const result = await backend.createWhatsAppTemplate(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió la plantilla creada." };
    }
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function deleteWhatsAppTemplateAction(
  tenantId: string,
  name: string,
): Promise<ActionResult<{ name: string; deleted: boolean }>> {
  await requireSession();
  try {
    const result = await backend.deleteWhatsAppTemplate(tenantId, name);
    if (!result) {
      return { ok: false, error: "El backend no confirmó el borrado." };
    }
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}
