"use server";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ReservasTemplates } from "@/lib/backend/reservas-templates";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Spec 043, requisito 15.7: how the six WhatsApp templates of Reservas stand, for
 * Ajustes. Same gate as every Reservas action — the person of a client with the
 * `reservas` module, a fresh 60 s token — and the API checks it again.
 */
async function reservasPrincipal() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok" || res.principal.kind !== "client") return null;
  return res.principal.modules.includes("reservas") ? res.principal : null;
}

export async function reservasTemplatesAction(): Promise<ActionResult<ReservasTemplates>> {
  const principal = await reservasPrincipal();
  if (!principal) return { ok: false, status: 403, message: "forbidden" };
  return run(() => backendFor(principal).reservasTemplates());
}
