/**
 * Spec 005 · lo que la consola sabe de la membresía.
 *
 * `weekly_pool_tokens` **no está aquí, y no es un olvido**: la API no lo
 * devuelve. Un nivel se describe por sus topes —números estables, porque
 * moverlos cambia el producto— y por `consumption_multiple`, que el servidor
 * calcula. La cifra del pool es provisional (ADR-037) y publicarla convertiría
 * cada ajuste de capacidad en un recorte o un regalo visible (research D9).
 */

export type TierOut = {
  code: "free" | "pro" | "team" | "business";
  display_name: string;
  monthly_price_cents: number;
  max_teammates: number;
  max_members: number;
  /** `null` en el gratuito y en cualquier proporción que no sea entera:
   *  decir «4×» de algo que es 3,7× es una promesa comercial falsa. */
  consumption_multiple: number | null;
};

export type SubscriptionState = "current" | "payment_failed" | "unpaid" | "canceled";

export type MembershipOut = {
  tier: TierOut;
  state: SubscriptionState;
  state_changed_at: string | null;
  current_period_end: string | null;
  pending_tier: string | null;
  usage: { teammates: number; members: number };
  purchased_expires_at: string | null;
  catalog: TierOut[];
};

export type CheckoutOut = {
  url: string | null;
  applied: boolean;
  effective_at: string | null;
};
