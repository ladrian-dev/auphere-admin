"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { Allocation } from "@/lib/backend/home-usage";
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
