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
import { type CheckoutOut, backendFor } from "@/lib/backend";
import { requirePrincipal } from "@/lib/principal";

const tierCode = z.enum(["pro", "team", "business"]);

export async function startCheckoutAction(raw: unknown): Promise<ActionResult<CheckoutOut>> {
  const { tier_code } = z.object({ tier_code: tierCode }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).startCheckout(tier_code));
  // Subir de plan no abre página: se aplica y hay que repintar.
  if (res.ok) revalidatePath("/billing");
  return res;
}

export async function openPortalAction(): Promise<ActionResult<{ url: string }>> {
  const principal = await requirePrincipal();
  return run(() => backendFor(principal).billingPortal());
}
