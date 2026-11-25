/**
 * Spec 077: the words of the send-only client, its keys and its membership.
 * Pure, so the server actions and the screens share them and the tests read
 * them without a server.
 */

/** Each closed `detail.code` of the API (contracts/admin-api.md), in the operator's words. */
export const SEND_ONLY_ERRORS: Record<string, string> = {
  tenant_not_found: "Este cliente ya no existe.",
  key_not_found: "Esa clave no es de este cliente.",
  key_already_revoked: "Esa clave ya estaba revocada.",
  no_membership: "Este cliente no tiene membresía.",
  no_partner: "Sin partner no se puede cobrar del saldo del partner.",
  subscription_in_progress:
    "Hay una suscripción de Stripe en curso. Para cambiar el importe o quién paga, cancélala y crea un enlace nuevo.",
  invalid_amount: "El importe no es válido.",
  membership_active: "La membresía está activa o tiene una suscripción viva. Cancélala antes de quitarla.",
  not_stripe: "Esta membresía no se cobra por Stripe.",
  already_active: "La membresía ya está activa: no hace falta otro enlace.",
  checkout_already_paid:
    "El enlace anterior ya se había pagado: la membresía se actualizó con ese pago y no se abrió otro.",
  billing_unavailable: "Stripe no responde ahora. Inténtalo en unos minutos.",
  not_wallet: "Esta membresía no se cobra del saldo del partner.",
};

/** The status of a template send, as the «Últimos envíos» table says it. Unknown values pass through. */
export function templateMessageStatus(status: string): { label: string; tone: "positive" | "neutral" | "danger" } {
  switch (status) {
    case "delivered":
      return { label: "Entregado", tone: "positive" };
    case "read":
      return { label: "Leído", tone: "positive" };
    case "sent":
      return { label: "Enviado", tone: "neutral" };
    case "pending":
      return { label: "En cola", tone: "neutral" };
    case "failed":
      return { label: "No se envió", tone: "danger" };
    default:
      return { label: status, tone: "neutral" };
  }
}

/** Why a send failed, when the panel knows the code; otherwise the code itself. */
export const FAILURE_LABEL: Record<string, string> = {
  membership_inactive: "membresía inactiva",
};

export const DEFAULT_MEMBERSHIP_CENTS = 4_000;

export type MembershipTone = "positive" | "info" | "warning" | "danger" | "muted";

/**
 * The membership's state in one pill. It follows `active` (what the sending
 * gate reads), not only `status`: a membership charged to the partner's
 * balance can say `active` with its period already over, and then it does
 * not send.
 */
export function membershipPill(m: { status: string; active: boolean }): { label: string; tone: MembershipTone } {
  if (m.status === "active") {
    return m.active ? { label: "Activa", tone: "positive" } : { label: "Periodo vencido", tone: "warning" };
  }
  if (m.status === "pending") return { label: "Pendiente de pago", tone: "info" };
  if (m.status === "past_due") return { label: "Impagada", tone: "danger" };
  if (m.status === "canceled") return { label: "Cancelada", tone: "muted" };
  return { label: m.status, tone: "muted" };
}

/**
 * The membership pill in a send-only client's header. Without a membership
 * there is none (the absence is designed); a membership that could not be
 * read says so, muted, instead of vanishing like «none».
 */
export function headerMembershipPill(
  membership: { status: string; active: boolean } | null | "error",
): { label: string; tone: MembershipTone } | null {
  if (membership === "error") return { label: "Membresía: sin leer", tone: "muted" };
  if (membership === null) return null;
  const pill = membershipPill(membership);
  return { label: `Membresía: ${pill.label.toLowerCase()}`, tone: pill.tone };
}

/** Who pays it, in the words of the design («bolsa» already names a client's pool, spec 047). */
export const PAYER_LABEL: Record<string, string> = {
  stripe: "El cliente, con tarjeta",
  partner_wallet: "Del saldo del partner",
};

export type KeyState = "active" | "grace" | "revoked" | "expired";

/** A key's state from its dates: revoked keys keep working until their grace ends. */
export function keyState(
  key: { revoked_at: string | null; grace_expires_at: string | null; expires_at: string | null },
  now: number = Date.now(),
): KeyState {
  if (key.revoked_at) {
    return key.grace_expires_at && new Date(key.grace_expires_at).getTime() > now ? "grace" : "revoked";
  }
  if (key.expires_at && new Date(key.expires_at).getTime() <= now) return "expired";
  return "active";
}

export const KEY_STATE: Record<KeyState, { label: string; tone: MembershipTone }> = {
  active: { label: "Activa", tone: "positive" },
  grace: { label: "En gracia", tone: "warning" },
  revoked: { label: "Revocada", tone: "muted" },
  expired: { label: "Caducada", tone: "muted" },
};
