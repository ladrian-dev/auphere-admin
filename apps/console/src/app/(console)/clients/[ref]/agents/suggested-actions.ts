"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { callFor } from "@/lib/backend";
import { suggestedAgentsApi } from "@/lib/backend/suggested-agents";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047, enmienda del 2026-10-29 (T210, requisito 60.6) — «Descartar» un
 * agente sugerido en la pestaña Agentes. Crear no pasa por aquí: «Crear este
 * agente» abre «Nuevo agente» relleno y el agente nace con su primer borrador,
 * como cualquier otro. La API vuelve a comprobar el permiso y el cliente.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const schema = z.object({
  ref: z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/),
  id: z.string().min(1).max(64).regex(/^[A-Za-z0-9_-]+$/),
});

export async function dismissSuggestedAgentAction(raw: unknown): Promise<ActionResult<null>> {
  const { ref, id } = schema.parse(raw);
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, "agents:write")) return forbidden;
  const res = await run(() => suggestedAgentsApi(callFor(principal)).dismissSuggestedAgent(ref, id));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(ref)}/agents`);
  return res;
}
