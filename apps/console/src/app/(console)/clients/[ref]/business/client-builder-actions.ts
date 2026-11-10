"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { QualityJob } from "@/lib/backend/agent-quality-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historia 18, T098) — «Completar con el constructor» en Negocio:
 * lanzar el trabajo y consultarlo. Sus propuestas quedan como sugerencias de la
 * ficha («Sugerido · confirma»), que se deciden una a una con la acción de
 * siempre (`decideSuggestionAction`); los agentes que propone vuelven en el
 * resultado y no se crean solos (18.4).
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);

async function partner(permission: "clients:read" | "clients:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

export async function startClientBuilderAction(raw: unknown): Promise<ActionResult<{ job_id: string }>> {
  const body = z.object({ ref }).parse(raw);
  const principal = await partner("clients:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).startClientBuilder(body.ref));
}

/** El trabajo `client_builder`, para la espera creciente. */
export async function clientBuilderJobAction(raw: unknown): Promise<ActionResult<QualityJob>> {
  const body = z.object({ ref, job: z.string().uuid() }).parse(raw);
  const principal = await partner("clients:read");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).getConsoleJob(body.job));
  if (res.ok && res.data.status === "done") revalidatePath(`/clients/${encodeURIComponent(body.ref)}/business`);
  return res;
}
