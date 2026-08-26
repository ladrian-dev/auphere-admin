"use server";

/**
 * Partner platform server actions (ADR-028).
 *
 * Same contract as ``tenants/actions.ts``: every mutation wraps the
 * backend call, revalidates the affected routes and returns a
 * ``Result<T>`` so the client can toast the backend's real error
 * message (409 slug tomado, 422 origin inválido, etc.) instead of a
 * generic one.
 *
 * IMPORTANT: actions that mint keys (`create` / `rotate`) return the
 * one-time ``plaintext``. It travels server → client exactly once for
 * the un-dismissable reveal dialog and is never persisted here.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend } from "@/lib/backend";
import { clearImpersonateCookie, setImpersonateCookie } from "@/lib/impersonate";
import { requireOperator } from "@/lib/session";
import type {
  PartnerApiKeyCreatedOut,
  PartnerApiKeyCreateInput,
  PartnerApiKeyOut,
  PartnerCreateInput,
  PartnerLlmOut,
  PartnerModelsOut,
  PartnerOut,
  PartnerTenantLinkInput,
  PartnerTenantOut,
  PartnerUpdateInput,
  PartnerWalletOut,
  TicketStatus,
  AdminTicketDetailOut,
  AdminImpersonateOut,
  ReceiptGenerateInput,
  ReceiptOut,
  ReceiptSendOut,
} from "@/lib/backend";

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

function err(e: unknown): { ok: false; error: string } {
  if (e instanceof BackendError) {
    const body = e.body as { detail?: string } | null;
    return {
      ok: false,
      error:
        typeof body?.detail === "string" ? body.detail : `HTTP ${e.status}`,
    };
  }
  return { ok: false, error: e instanceof Error ? e.message : String(e) };
}

// ── partner CRUD ─────────────────────────────────────────────────────────────

export async function createPartnerAction(
  body: PartnerCreateInput,
): Promise<ActionResult<PartnerOut>> {
  try {
    const r = await backend.createPartner(body);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath("/partners");
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

export async function updatePartnerAction(
  partnerId: string,
  body: PartnerUpdateInput,
): Promise<ActionResult<PartnerOut>> {
  try {
    const r = await backend.updatePartner(partnerId, body);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath("/partners");
    revalidatePath(`/partners/${partnerId}`);
    revalidatePath(`/partners/${partnerId}/limits`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

// ── API keys ─────────────────────────────────────────────────────────────────

export async function createPartnerKeyAction(
  partnerId: string,
  body: PartnerApiKeyCreateInput,
): Promise<ActionResult<PartnerApiKeyCreatedOut>> {
  try {
    const r = await backend.createPartnerKey(partnerId, body);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

export async function rotatePartnerKeyAction(
  partnerId: string,
  keyId: string,
  graceHours: number,
): Promise<ActionResult<PartnerApiKeyCreatedOut>> {
  try {
    const r = await backend.rotatePartnerKey(partnerId, keyId, {
      grace_hours: graceHours,
    });
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

export async function revokePartnerKeyAction(
  partnerId: string,
  keyId: string,
): Promise<ActionResult<PartnerApiKeyOut>> {
  try {
    const r = await backend.revokePartnerKey(partnerId, keyId);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

// ── tenant mappings ──────────────────────────────────────────────────────────

export async function linkPartnerTenantAction(
  partnerId: string,
  body: PartnerTenantLinkInput,
): Promise<ActionResult<PartnerTenantOut>> {
  try {
    const r = await backend.linkPartnerTenant(partnerId, body);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}/tenants`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

// ── recibos mensuales ────────────────────────────────────────────────────────

export async function generateReceiptAction(
  partnerId: string,
  body: ReceiptGenerateInput,
): Promise<ActionResult<ReceiptOut>> {
  try {
    const r = await backend.generatePartnerReceipt(partnerId, body);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}/receipts`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

export async function sendReceiptAction(
  partnerId: string,
  invoiceId: string,
): Promise<ActionResult<ReceiptSendOut>> {
  try {
    const r = await backend.sendPartnerReceipt(partnerId, invoiceId);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}/receipts`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

// ── C3 wallet (admin recharge) ───────────────────────────────────────────────

export async function rechargePartnerWallet(
  partnerId: string,
  qty: number,
): Promise<ActionResult<PartnerWalletOut>> {
  try {
    const r = await backend.rechargePartnerWallet(partnerId, qty);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}/wallet`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

// ── F2 models + LiteLLM block ───────────────────────────────────────────────

export async function setPartnerModels(
  partnerId: string,
  modelIds: string[],
): Promise<ActionResult<PartnerModelsOut>> {
  try {
    const r = await backend.putPartnerModels(partnerId, modelIds);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}/models`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

export async function blockPartnerLlm(
  partnerId: string,
  blocked: boolean,
): Promise<ActionResult<PartnerLlmOut>> {
  try {
    const r = await backend.blockPartnerLlm(partnerId, blocked);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath(`/partners/${partnerId}/models`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}


export async function patchTicketStatus(
  ticketId: string,
  status: TicketStatus,
): Promise<ActionResult<AdminTicketDetailOut>> {
  try {
    const r = await backend.patchTicketStatus(ticketId, status);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    revalidatePath("/tickets");
    revalidatePath(`/tickets/${ticketId}`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}


// ── F5 impersonation (admin cookie only) ───────────────────────────────────

export async function startImpersonationAction(
  partnerId: string,
  reason: string,
  ttlSeconds: number,
): Promise<ActionResult<AdminImpersonateOut>> {
  try {
    const operator = await requireOperator();
    const r = await backend.startImpersonation(
      partnerId,
      { reason, ttl_seconds: ttlSeconds },
      operator.id,
    );
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    await setImpersonateCookie(r.id, r.ttl_seconds);
    revalidatePath(`/partners/${partnerId}`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}

export async function revokeImpersonationAction(
  sessionId: string,
): Promise<ActionResult<AdminImpersonateOut>> {
  try {
    const operator = await requireOperator();
    const r = await backend.revokeImpersonation(sessionId, operator.id);
    if (!r) return { ok: false, error: "Respuesta vacía del backend" };
    await clearImpersonateCookie();
    revalidatePath(`/partners/${r.partner_id}`);
    return { ok: true, data: r };
  } catch (e) {
    return err(e);
  }
}
