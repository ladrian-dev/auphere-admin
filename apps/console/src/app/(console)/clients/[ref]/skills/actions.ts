"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { SkillsSaved } from "@/lib/backend/agent-tools";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Actions of lane `agent-tools` — vertical skills (CP-14). */

export async function saveSkillsAction(raw: unknown): Promise<ActionResult<SkillsSaved>> {
  const body = z.object({ ref: z.string().min(1).max(255), skills: z.array(z.string().min(1).max(200)).max(50) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).putSkills(body.ref, body.skills));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}
