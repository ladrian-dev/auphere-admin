"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { Allocation, Wallet } from "@/lib/backend/home-usage";
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

const purchasedSchema = z.object({
  qty: z.number().int().positive(),
});

export async function addPurchasedAction(raw: unknown): Promise<ActionResult<Wallet>> {
  const body = purchasedSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "usage:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).addPurchased(body.qty));
  if (res.ok) revalidatePath("/usage");
  return res;
}

const moveSchema = z.object({
  from_ref: z.string().min(1).max(255),
  to_ref: z.string().min(1).max(255),
  from_cap: z.number().int().min(0),
  to_cap: z.number().int().min(0),
  qty: z.number().int().positive(),
});

export async function moveAllocationAction(raw: unknown): Promise<ActionResult<Allocation>> {
  const body = moveSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "usage:write")) return { ok: false, status: 403, message: "forbidden" };
  if (body.from_ref === body.to_ref) return { ok: false, status: 422, message: "same client" };
  if (body.qty > body.from_cap) return { ok: false, status: 422, message: "qty" };
  const api = backendFor(principal);
  const lowered = await run(() => api.setAllocation(body.from_ref, body.from_cap - body.qty));
  if (!lowered.ok) return lowered;
  const raised = await run(() => api.setAllocation(body.to_ref, body.to_cap + body.qty));
  revalidatePath("/usage");
  return raised;
}
