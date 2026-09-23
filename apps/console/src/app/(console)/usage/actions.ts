"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { Allocation, AllocationMove } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";

const schema = z.object({
  client_ref: z.string().min(1).max(255),
  cap: z.number().int().min(0),
});

export async function saveAllocationAction(raw: unknown): Promise<ActionResult<Allocation>> {
  const body = schema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "usage:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).setAllocation(body.client_ref, body.cap));
  if (res.ok) revalidatePath("/usage");
  return res;
}

// ``addPurchasedAction`` se borró con la spec 005, con la ruta que llamaba.
// Acreditarse saldo sin pagar era un juguete de desarrollo apagado por
// entorno; ahora la compra es real y vive en ``billing/actions.ts``.

const moveSchema = z.object({
  from_ref: z.string().min(1).max(255),
  to_ref: z.string().min(1).max(255),
  qty: z.number().int().positive(),
});

/**
 * Spec 016 (R3.1): ONE backend call. The API moves the quota in a single
 * transaction and answers by code (`same_client`, `insufficient_cap` with
 * the cap) — the screen writes the sentence from that.
 */
export async function moveAllocationAction(raw: unknown): Promise<ActionResult<AllocationMove>> {
  const body = moveSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "usage:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).moveAllocation(body.from_ref, body.to_ref, body.qty));
  if (res.ok) revalidatePath("/usage");
  return res;
}
