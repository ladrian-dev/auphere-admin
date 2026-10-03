"use server";

/**
 * Spec 005 · las acciones de la pantalla de planes.
 *
 * Ninguna de las tres maneja dinero: abren la página del proveedor y
 * devuelven su URL. **La consola no lleva ninguna credencial del proveedor**
 * —igual que no lleva ninguna del backend—, así que el token de 60 segundos
 * llega a la API y es ella quien habla con Stripe.
 */

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { type ActionResult, run } from "@/lib/actions";
import { type CancelOut, type CheckoutOut, backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/** Spec 016 (R8.1): every billing action is `billing:manage` — the API's own permission. */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

const tierCode = z.enum(["pro", "team", "business"]);

export async function startCheckoutAction(raw: unknown): Promise<ActionResult<CheckoutOut>> {
  const { tier_code } = z.object({ tier_code: tierCode }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "billing:manage")) return forbidden;
  const res = await run(() => backendFor(principal).startCheckout(tier_code));
  // Subir de plan no abre página: se aplica y hay que repintar.
  if (res.ok) revalidatePath("/billing");
  return res;
}

export async function buyCreditAction(raw: unknown): Promise<ActionResult<CheckoutOut>> {
  // Los mismos límites que la API. Duplicarlos aquí no es redundancia: el
  // formulario ya los aplica para no rebotar contra un 422, y esta capa los
  // vuelve a aplicar porque una server action es una entrada, no una pantalla.
  const { amount_cents } = z
    .object({ amount_cents: z.number().int().min(500).max(500_000) })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "billing:manage")) return forbidden;
  const res = await run(() => backendFor(principal).buyCredit(amount_cents));
  if (res.ok) revalidatePath("/usage");
  return res;
}

export async function openPortalAction(): Promise<ActionResult<{ url: string }>> {
  const principal = await requirePrincipal();
  if (!can(principal.role, "billing:manage")) return forbidden;
  return run(() => backendFor(principal).billingPortal());
}

export async function cancelSubscriptionAction(): Promise<ActionResult<CancelOut>> {
  const principal = await requirePrincipal();
  if (!can(principal.role, "billing:manage")) return forbidden;
  const res = await run(() => backendFor(principal).cancelSubscription());
  if (res.ok) revalidatePath("/billing");
  return res;
}
