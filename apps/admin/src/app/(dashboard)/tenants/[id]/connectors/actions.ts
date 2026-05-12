"use server";

/**
 * Server actions for the per-tenant connectors panel.
 *
 * All mutations go through the backend admin API (RLS-enforced). Each
 * action returns a discriminated union so the client can show a toast
 * with the upstream error message instead of swallowing the failure.
 */

import { revalidatePath } from "next/cache";

import { BackendError, backend, type ConnectorToolMode } from "@/lib/backend";

export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

function err(e: unknown): { ok: false; error: string } {
  if (e instanceof BackendError) {
    const body = e.body as { detail?: string } | null;
    return {
      ok: false,
      error: body?.detail ?? `HTTP ${e.status}`,
    };
  }
  return { ok: false, error: e instanceof Error ? e.message : String(e) };
}

export async function initiateConsentAction(
  tenantId: string,
  slug: string,
): Promise<ActionResult<{ redirect_url: string; signed_consent_url: string; expires_at: string }>> {
  try {
    const r = await backend.initiateConnectorConsent(tenantId, slug);
    if (!r) return { ok: false, error: "empty response" };
    revalidatePath(`/tenants/${tenantId}/connectors`);
    return {
      ok: true,
      data: {
        redirect_url: r.redirect_url,
        signed_consent_url: r.signed_consent_url,
        expires_at: r.expires_at,
      },
    };
  } catch (e) {
    return err(e);
  }
}

export async function disconnectAction(
  tenantId: string,
  slug: string,
): Promise<ActionResult<string>> {
  try {
    const r = await backend.disconnectConnector(tenantId, slug);
    revalidatePath(`/tenants/${tenantId}/connectors`);
    return { ok: true, data: r?.status ?? "disconnected" };
  } catch (e) {
    return err(e);
  }
}

export async function syncAction(
  tenantId: string,
  slug: string,
): Promise<ActionResult<{ added: number; deprecated: number; unchanged: number }>> {
  try {
    const r = await backend.syncConnector(tenantId, slug);
    revalidatePath(`/tenants/${tenantId}/connectors`);
    if (!r) return { ok: false, error: "empty response" };
    return {
      ok: true,
      data: {
        added: r.added.length,
        deprecated: r.deprecated.length,
        unchanged: r.unchanged_count,
      },
    };
  } catch (e) {
    return err(e);
  }
}

export async function reissueConsentAction(
  tenantId: string,
  slug: string,
): Promise<ActionResult<{ signed_consent_url: string; expires_at: string }>> {
  try {
    const r = await backend.reissueConnectorConsent(tenantId, slug);
    revalidatePath(`/tenants/${tenantId}/connectors`);
    if (!r) return { ok: false, error: "empty response" };
    return {
      ok: true,
      data: {
        signed_consent_url: r.signed_consent_url,
        expires_at: r.expires_at,
      },
    };
  } catch (e) {
    return err(e);
  }
}

export async function putOverrideAction(
  tenantId: string,
  toolName: string,
  mode: ConnectorToolMode,
  reason: string | null,
): Promise<ActionResult<{ mode: ConnectorToolMode }>> {
  try {
    const r = await backend.putConnectorToolOverride(tenantId, toolName, {
      mode,
      reason,
    });
    revalidatePath(`/tenants/${tenantId}/connectors`);
    return { ok: true, data: { mode: (r?.mode as ConnectorToolMode) ?? mode } };
  } catch (e) {
    return err(e);
  }
}

export async function deleteOverrideAction(
  tenantId: string,
  toolName: string,
): Promise<ActionResult<void>> {
  try {
    await backend.deleteConnectorToolOverride(tenantId, toolName);
    revalidatePath(`/tenants/${tenantId}/connectors`);
    return { ok: true, data: undefined };
  } catch (e) {
    return err(e);
  }
}
