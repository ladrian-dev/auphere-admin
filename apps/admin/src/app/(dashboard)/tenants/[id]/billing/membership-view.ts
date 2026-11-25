import type { MembershipOut } from "@/lib/backend";
import { formatCents, longDate } from "@/lib/format";
import { membershipPill, type MembershipTone } from "@/lib/send-only";

/** What a Stripe or wallet failure means, in words. Unknown codes pass through. */
const FAILURE: Record<string, string> = {
  insufficient_balance: "el partner no tenía saldo",
  card_declined: "la tarjeta fue rechazada",
  expired_card: "la tarjeta está caducada",
};

export type MembershipLink =
  | { kind: "none" }
  | { kind: "create"; label: string }
  | { kind: "live"; url: string; expiresAt: string | null }
  | { kind: "expired"; expiredAt: string | null };

export type MembershipView = {
  pill: { label: string; tone: MembershipTone };
  /** Renewal, period end or why it failed. */
  sub: string;
  /** Whether the API sends — from `active`, the gate's own reading. */
  sends: boolean;
  notice: string;
  noticeTone: MembershipTone;
  isStripe: boolean;
  /** Wallet: the amount that applies from the next period. */
  pendingAmount: string | null;
  link: MembershipLink;
  canRefresh: boolean;
  canCharge: boolean;
  /** `null`: it can change; a string: why it cannot. */
  amountLocked: string | null;
  canCancel: boolean;
  canArchive: boolean;
};

/**
 * Spec 077 (T027): the membership card from `MembershipOut`, pure so every
 * state is tested without a server. The card never claims more than the API
 * said: «sends» follows `active`, the expiry of a payment link is read from
 * the API, and an amount change is refused while a Stripe subscription lives.
 */
export function membershipView(m: MembershipOut, now: number = Date.now()): MembershipView {
  const isStripe = m.payer === "stripe";
  const pill = membershipPill(m);
  const failure = m.last_failure ? (FAILURE[m.last_failure] ?? m.last_failure) : null;
  const periodEnd = m.current_period_end ? longDate(m.current_period_end) : null;
  const periodLive = m.current_period_end ? new Date(m.current_period_end).getTime() > now : false;

  let sub: string;
  let notice: string;
  let noticeTone: MembershipTone;
  if (m.active) {
    sub = periodEnd ? (isStripe ? `Se renueva el ${periodEnd}.` : `Pagada hasta el ${periodEnd}; entonces se cobra del saldo.`) : "Al día.";
    notice = "Los envíos salen con normalidad.";
    noticeTone = "positive";
  } else if (m.status === "pending") {
    sub = isStripe ? "Se activa cuando el cliente pague." : "Se activa al descontarse del saldo del partner.";
    notice = "Su API no envía hasta el primer cobro.";
    noticeTone = "info";
  } else if (m.status === "past_due") {
    sub = isStripe
      ? `Stripe no pudo cobrar${failure ? `: ${failure}` : ""}.`
      : `No se pudo cobrar del saldo${failure ? `: ${failure}` : ""}. Se reintenta solo hasta que haya saldo.`;
    notice = "Envíos detenidos: la API responde 402 y lo que estaba en cola no sale.";
    noticeTone = "danger";
  } else if (m.status === "canceled") {
    sub = periodEnd && periodLive ? `Cancelada. Estaba pagada hasta el ${periodEnd}.` : "Cancelada. No se cobra nada más.";
    notice = "Envíos detenidos. Vuelve con un cobro nuevo.";
    noticeTone = "muted";
  } else {
    // `active` with its wallet period over: the gate does not let it send.
    sub = periodEnd ? `El periodo pagado terminó el ${periodEnd} y no se ha cobrado el siguiente.` : "Sin periodo pagado.";
    notice = "Envíos detenidos hasta que se cobre el periodo.";
    noticeTone = "warning";
  }

  let link: MembershipLink = { kind: "none" };
  if (isStripe && !m.active && !m.has_subscription) {
    if (m.checkout_url) {
      const expired = m.checkout_expires_at ? new Date(m.checkout_expires_at).getTime() <= now : false;
      link = expired
        ? { kind: "expired", expiredAt: m.checkout_expires_at }
        : { kind: "live", url: m.checkout_url, expiresAt: m.checkout_expires_at };
    } else {
      link = { kind: "create", label: m.status === "past_due" ? "Crear enlace para pagar" : "Crear enlace de pago" };
    }
  }

  return {
    pill,
    sub,
    sends: m.active,
    notice,
    noticeTone,
    isStripe,
    pendingAmount:
      !isStripe && m.pending_amount_cents != null && m.pending_amount_cents !== m.amount_cents
        ? formatCents(m.pending_amount_cents)
        : null,
    link,
    canRefresh: isStripe,
    canCharge: !isStripe && !m.active && m.status !== "canceled",
    amountLocked: m.has_subscription
      ? "Hay una suscripción de Stripe en curso. Para cambiar el importe, cancélala y crea un enlace nuevo."
      : null,
    canCancel: m.status !== "canceled",
    canArchive: m.status !== "active" && !m.has_subscription,
  };
}

/** A charge's state, as the «Cobros» table says it. Unknown values pass through. */
export function chargeStatus(status: string): { label: string; tone: MembershipTone } {
  switch (status) {
    case "paid":
      return { label: "Pagado", tone: "positive" };
    case "open":
      return { label: "Pendiente", tone: "info" };
    case "failed":
      return { label: "No se pudo cobrar", tone: "danger" };
    case "void":
      return { label: "Anulado", tone: "muted" };
    default:
      return { label: status, tone: "muted" };
  }
}
