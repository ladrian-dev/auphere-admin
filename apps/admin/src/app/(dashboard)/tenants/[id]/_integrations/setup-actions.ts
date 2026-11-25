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
import { z } from "zod";

import { BackendError, backend } from "@/lib/backend";
import type {
  MetaConnectOwnedInput,
  MetaSignupInput,
  MetaSignupResult,
  MetaTestSendInput,
  MetaTestSendResult,
  WhatsAppTemplateCreateInput,
  WhatsAppTemplateCreateResult,
  WhatsAppTemplateEditInput,
  WhatsAppTemplateEditResult,
  WhatsAppTemplateList,
} from "@/lib/backend";
import { requireOperator } from "@/lib/session";

export type ActionResult<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      error: string;
      /** Closed-vocabulary code when the API answered with a structured
       *  ``detail`` (spec 075); the screen writes the sentence from it. */
      code?: string | null;
      /** The rest of that structured detail (reasons, variables, Meta's codes). */
      info?: Record<string, unknown>;
    };

function toError(err: unknown): string {
  if (err instanceof BackendError) {
    const detail = (err.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    // A FastAPI validation error carries a list: the screens paint this as text.
    return detail ? `La API no aceptó la petición (HTTP ${err.status}).` : `HTTP ${err.status}`;
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
  await requireOperator();
  try {
    const result = await backend.metaSignup(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió datos del signup." };
    }
    await backend.connectManualConnector(tenantId, "whatsapp_meta", {
      channel_id: result.channel_id,
    });
    revalidatePath(`/tenants/${tenantId}`, "layout");
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
  await requireOperator();
  try {
    const result = await backend.metaConnectOwned(tenantId, body);
    if (!result) {
      return { ok: false, error: "El backend no devolvió datos de la conexión." };
    }
    await backend.connectManualConnector(tenantId, "whatsapp_meta", {
      channel_id: result.channel_id,
    });
    revalidatePath(`/tenants/${tenantId}`, "layout");
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
  await requireOperator();
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
/** Spec 050: rotate the number's two-step PIN (Cloud API only). */
export async function rotateWhatsAppPinAction(
  tenantId: string,
  channelId: string,
): Promise<ActionResult<null>> {
  await requireOperator();
  try {
    await backend.rotateWhatsAppPin(tenantId, channelId);
    revalidatePath(`/tenants/${tenantId}/channels/${channelId}`);
    return { ok: true, data: null };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

export async function tiktokAuthorizeUrlAction(
  tenantId: string,
): Promise<ActionResult<{ authorize_url: string }>> {
  await requireOperator();
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
  await requireOperator();
  try {
    const result = await backend.tiktokDisconnect(tenantId);
    if (!result) {
      return { ok: false, error: "El backend no confirmó la desconexión." };
    }
    revalidatePath(`/tenants/${tenantId}`, "layout");
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
  await requireOperator();
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
    revalidatePath(`/tenants/${tenantId}`, "layout");
    revalidatePath(`/tenants/${tenantId}`);
    return { ok: true, data: { store_url: storeUrl } };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

// ── WhatsApp template (HSM) management ─────────────────────────────────────

export async function listWhatsAppTemplatesAction(
  tenantId: string,
): Promise<ActionResult<WhatsAppTemplateList>> {
  await requireOperator();
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

export async function deleteWhatsAppTemplateAction(
  tenantId: string,
  name: string,
): Promise<ActionResult<{ name: string; deleted: boolean }>> {
  await requireOperator();
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

// Spec 075: create a template (10.5) and edit one language of one, keeping its name.

const TENANT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const editButton = z.object({
  type: z.enum(["QUICK_REPLY", "URL", "PHONE_NUMBER"]),
  label: z.string().min(1).max(25),
  url: z.string().url().max(2000).optional(),
  phone_number: z.string().max(20).optional(),
});

const templateName = z.string().regex(/^[a-z0-9_]{1,512}$/);
const templateLanguage = z.string().regex(/^[A-Za-z]{2,3}(_[A-Za-z0-9]{2,8})?$/);
const templateExamples = z.record(z.string().regex(/^[a-z0-9_]{1,40}$/), z.string().min(1).max(200)).default({});

/** Spec 075 (10.5), 077 (3.4): the console's create shape; Authentication carries `otp_*`, never a body. */
const createBody = z.discriminatedUnion("category", [
  z
    .object({
      name: templateName,
      language: templateLanguage,
      category: z.enum(["MARKETING", "UTILITY"]),
      header_text: z.string().max(60).optional(),
      body_text: z.string().min(1).max(1024),
      footer_text: z.string().max(60).optional(),
      buttons: z.array(editButton).max(3).default([]),
      examples: templateExamples,
    })
    .strict(),
  z
    .object({
      name: templateName,
      language: templateLanguage,
      category: z.literal("AUTHENTICATION"),
      otp_button_text: z.string().trim().min(1).max(25),
      otp_expiration_minutes: z.number().int().min(1).max(90).optional(),
      otp_security_recommendation: z.boolean(),
    })
    .strict(),
]);

/**
 * Spec 075 (10.5): the panel creates with the console's shape — what the shared
 * editor hands over — and the API builds what goes to Meta (9.3). The operator
 * is required **first**; what is not that shape never reaches the API.
 */
export async function createWhatsAppTemplateAction(
  tenantId: string,
  body: WhatsAppTemplateCreateInput,
): Promise<ActionResult<WhatsAppTemplateCreateResult>> {
  await requireOperator();
  const content = createBody.safeParse(body);
  if (!TENANT_ID_RE.test(tenantId) || !content.success) {
    return { ok: false, error: "La plantilla o el cliente no son válidos.", code: "invalid" };
  }
  const data =
    content.data.category === "AUTHENTICATION"
      ? content.data
      : { ...content.data, header_text: content.data.header_text || undefined, footer_text: content.data.footer_text || undefined };
  try {
    const result = await backend.createWhatsAppTemplate(tenantId, data);
    if (!result) {
      return { ok: false, error: "El backend no devolvió la plantilla creada." };
    }
    return { ok: true, data: result };
  } catch (err) {
    return { ok: false, error: toError(err) };
  }
}

const editTarget = z.object({
  tenantId: z.string().regex(TENANT_ID_RE),
  name: templateName,
  language: templateLanguage,
});

const editBody = z.object({
  version: z.string().regex(/^[0-9a-f]{16}$/),
  confirm: z.boolean().default(false),
  category: z.enum(["MARKETING", "UTILITY", "AUTHENTICATION"]).optional(),
  header_text: z.string().max(60).optional(),
  body_text: z.string().min(1).max(1024),
  footer_text: z.string().max(60).optional(),
  buttons: z.array(editButton).max(3).default([]),
  examples: templateExamples,
});

/** The API's structured ``detail`` → code + the rest, so the dialog can say it in words. */
function toEditFailure(err: unknown): { ok: false; error: string; code: string | null; info: Record<string, unknown> } {
  if (err instanceof BackendError) {
    const detail = (err.body as { detail?: unknown } | null)?.detail;
    if (detail && typeof detail === "object" && typeof (detail as { code?: unknown }).code === "string") {
      const { code, ...info } = detail as { code: string } & Record<string, unknown>;
      return { ok: false, error: code, code, info };
    }
    return { ok: false, error: typeof detail === "string" ? detail : `HTTP ${err.status}`, code: null, info: { status: err.status } };
  }
  return { ok: false, error: err instanceof Error ? err.message : String(err), code: null, info: {} };
}

/**
 * Spec 075 (9.1, 8.3): the operator edits a client's template from the panel.
 * The operator is required **first** — a panel Server Action without it was a
 * P0 of the 2026-11-22 security review — and named to the API with
 * ``X-Operator-Id``, so the audit records the person, not the panel's token.
 */
export async function editWhatsAppTemplateAction(
  tenantId: string,
  name: string,
  language: string,
  body: WhatsAppTemplateEditInput,
): Promise<ActionResult<WhatsAppTemplateEditResult>> {
  const operator = await requireOperator();
  const target = editTarget.safeParse({ tenantId, name, language });
  const content = editBody.safeParse(body);
  if (!target.success || !content.success) {
    return { ok: false, error: "La plantilla o el cliente no son válidos.", code: "invalid", info: {} };
  }
  try {
    const result = await backend.editWhatsAppTemplate(
      target.data.tenantId,
      target.data.name,
      target.data.language,
      {
        ...content.data,
        header_text: content.data.header_text || undefined,
        footer_text: content.data.footer_text || undefined,
      },
      operator.id,
    );
    if (!result) {
      return { ok: false, error: "El backend no devolvió la plantilla editada.", code: null, info: {} };
    }
    return { ok: true, data: result };
  } catch (err) {
    return toEditFailure(err);
  }
}
