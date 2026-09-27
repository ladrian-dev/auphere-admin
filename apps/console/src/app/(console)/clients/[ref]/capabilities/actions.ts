"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { CapabilityUpdated } from "@/lib/backend/capabilities";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 017 (R5.4): un clic enciende o apaga, y eso ya queda en el borrador.
 *
 * **Un cambio por llamada.** La pantalla vieja mandaba la lista blanca
 * entera en cada guardado, así que dos personas editando el mismo cliente a
 * la vez se pisaban sin enterarse. Aquí se nombra la capacidad y lo que
 * cambia de ella.
 */
const schema = z
  .object({
    ref: z.string().min(1).max(255),
    key: z.string().min(1).max(128),
    kind: z.enum(["tool", "skill"]),
    enabled: z.boolean().optional(),
    // `needs_approval` no está: la pantalla no puede ni pedirlo (R5.7). La
    // API lo rechaza igualmente, pero el error más barato es el que no sale.
    mode: z.enum(["always", "blocked"]).optional(),
  })
  .refine((v) => v.enabled !== undefined || v.mode !== undefined, {
    message: "nothing_to_change",
  });

export async function setCapabilityAction(raw: unknown): Promise<ActionResult<CapabilityUpdated>> {
  const { ref, ...change } = schema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return { ok: false, status: 403, message: "forbidden" };
  const res = await run(() => backendFor(principal).setCapability(ref, change));
  // La barra de borrador vive en el layout de la ficha: al encender algo
  // tiene que aparecer en TODAS las pestañas, no solo en esta.
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(ref)}`, "layout");
  return res;
}
