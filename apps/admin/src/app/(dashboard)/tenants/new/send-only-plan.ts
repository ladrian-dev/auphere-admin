import type { MembershipPayer } from "@/lib/backend";
import { parseUsdToCents } from "@/lib/money";

import type { SendOnlyFollowUp } from "./actions";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** The «Auphere (directo)» option of the partner select: no partner. */
export const DIRECT = "__direct__";

export type SendOnlyDraft = {
  partner: string;
  requireMembership: boolean;
  payer: MembershipPayer;
  amount: string;
  email: string;
};

export type SendOnlyPlan =
  | { ok: true; followUp: SendOnlyFollowUp }
  | { ok: false; errors: { amount?: string; email?: string; payer?: string } };

/**
 * Spec 077 (T024): what the wizard saves after creating a send-only client.
 * The partner is optional (empty = a direct Auphere client); the membership is
 * optional, and «Del saldo del partner» only exists with a partner. Pure, so
 * every combination is tested without a server.
 */
export function sendOnlyPlan(draft: SendOnlyDraft): SendOnlyPlan {
  const partnerId = draft.partner && draft.partner !== DIRECT ? draft.partner : null;
  if (!draft.requireMembership) return { ok: true, followUp: { partnerId, membership: null } };

  const errors: { amount?: string; email?: string; payer?: string } = {};
  const cents = parseUsdToCents(draft.amount);
  if (cents === null) errors.amount = "Escribe un importe, por ejemplo 40,00.";
  if (draft.payer === "partner_wallet" && !partnerId) errors.payer = "Sin partner no hay saldo del que cobrar.";
  if (draft.payer === "stripe" && !EMAIL_RE.test(draft.email.trim())) {
    errors.email = "Escribe el correo al que Stripe manda sus facturas.";
  }
  if (cents === null || Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    followUp: {
      partnerId,
      membership: {
        payer: draft.payer,
        amount_cents: cents,
        billing_email: draft.payer === "stripe" ? draft.email.trim() : null,
      },
    },
  };
}
