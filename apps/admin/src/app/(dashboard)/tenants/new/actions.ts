"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { backend, BackendError } from "@/lib/backend";
import type { MembershipPayer, TenantCreateInput } from "@/lib/backend";
import { toCodedFailure } from "@/lib/action-result";
import { SEND_ONLY_ERRORS } from "@/lib/send-only";
import { requireOperator } from "@/lib/session";

export type CreateTenantState =
  | { kind: "error"; message: string }
  | { kind: "ok"; tenantId: string };

export async function createTenantAction(
  input: TenantCreateInput,
): Promise<CreateTenantState> {
  // Before the try: without a session it redirects, and the catch would swallow that.
  const operator = await requireOperator();
  try {
    const tenant = await backend.createTenant(input, operator.id);
    if (!tenant) {
      return { kind: "error", message: "El backend no devolvió el tenant creado." };
    }
    // Redirect happens client-side after the success state propagates so the
    // form can show a toast first. The new tenant id is returned to the form.
    return { kind: "ok", tenantId: tenant.id };
  } catch (err) {
    if (err instanceof BackendError) {
      const detail =
        typeof err.body === "object" && err.body !== null && "detail" in err.body
          ? String((err.body as { detail: unknown }).detail)
          : err.message;
      return { kind: "error", message: detail };
    }
    return {
      kind: "error",
      message: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function checkSlugAction(slug: string): Promise<{ available: boolean }> {
  try {
    const result = await backend.checkSlugAvailability(slug);
    return { available: result?.available ?? false };
  } catch {
    // If the network probe fails, fall back to permissive (the POST will
    // 409 if there's a real conflict). Don't block the form.
    return { available: true };
  }
}

export async function gotoTenantIntegrations(tenantId: string): Promise<never> {
  redirect(`/tenants/${tenantId}/channels/new`);
}

/** Spec 077 (T024): what a send-only client may still need once it exists. */
export type SendOnlyFollowUp = {
  /** `null`: a direct Auphere client — nothing to save. */
  partnerId: string | null;
  membership: { payer: MembershipPayer; amount_cents: number; billing_email: string | null } | null;
};

/**
 * Spec 077 (T024): after `POST /admin/tenants`, the partner (through the
 * billing that already exists) and then the membership — in that order,
 * because a charge to the partner's balance needs the partner first. The
 * client already exists, so a failure here never undoes it: it is said, and
 * the operator finishes it from the client's page.
 */
export async function finishSendOnlySetupAction(
  tenantId: string,
  followUp: SendOnlyFollowUp,
): Promise<{ notSaved: string[] }> {
  // Every write here names the operator, the partner one too.
  const operator = await requireOperator();
  const notSaved: string[] = [];
  if (followUp.partnerId) {
    try {
      await backend.updateTenantBilling(tenantId, { partner_id: followUp.partnerId }, operator.id);
    } catch (err) {
      notSaved.push(`el partner (${toCodedFailure(err, SEND_ONLY_ERRORS).error})`);
      // Without the partner, a charge to its balance cannot exist either.
      if (followUp.membership?.payer === "partner_wallet") {
        notSaved.push("la membresía (necesita el partner)");
        return { notSaved };
      }
    }
  }
  if (followUp.membership) {
    try {
      await backend.putMembership(
        tenantId,
        {
          payer: followUp.membership.payer,
          amount_cents: followUp.membership.amount_cents,
          ...(followUp.membership.billing_email ? { billing_email: followUp.membership.billing_email } : {}),
        },
        operator.id,
      );
    } catch (err) {
      notSaved.push(`la membresía (${toCodedFailure(err, SEND_ONLY_ERRORS).error})`);
    }
  }
  revalidatePath(`/tenants/${tenantId}`, "layout");
  return { notSaved };
}
