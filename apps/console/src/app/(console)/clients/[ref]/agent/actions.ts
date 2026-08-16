"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { consolePolicySchema } from "@/components/agent-tools/settings-schema";
import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { AgentSettingsSaved, ConsolePolicy } from "@/lib/backend/agent-tools";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Actions of lane `agent-tools` — structured settings (CP-11 / CP-31).
 *  Zod on the server (same schema as the form), `run()` for backend errors,
 *  `can()` before the write. */

const ref = z.string().min(1).max(255);

export async function saveAgentSettingsAction(raw: unknown): Promise<ActionResult<AgentSettingsSaved>> {
  const body = z.object({ ref, settings: consolePolicySchema }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).putAgentSettings(body.ref, body.settings as ConsolePolicy));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/agent`, "layout");
  return res;
}
