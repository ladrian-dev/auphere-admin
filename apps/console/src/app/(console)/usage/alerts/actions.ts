"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { UsageAlerts } from "@/lib/backend/home-usage";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Action of the usage-alerts form (CP-24). Zod on the server; the API decides. */
const schema = z.object({
  cap_messages_month: z.number().int().min(0).max(1_000_000_000).nullable(),
  recipients: z.array(z.string().email().max(255)).max(20),
  enabled: z.boolean(),
});

export async function saveUsageAlertsAction(raw: unknown): Promise<ActionResult<UsageAlerts>> {
  const body = schema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "usage:manage")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).setUsageAlerts(body));
  if (res.ok) {
    revalidatePath("/usage/alerts");
    revalidatePath("/usage");
    revalidatePath("/");
  }
  return res;
}
