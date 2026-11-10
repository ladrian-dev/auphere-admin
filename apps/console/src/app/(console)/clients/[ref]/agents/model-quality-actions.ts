"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { ModelQuality, QualityCheckAccepted } from "@/lib/backend/model-quality-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historia 23; T147; requisito 39) — Agente › Avanzado › Calidad:
 * leer las opciones con su precio estimado y «Comprobar la calidad» de una
 * (un trabajo que se consulta con `qualityJobAction`, como las pruebas).
 *
 * Elegir la opción no se hace aquí: la política viaja en el AgentSpec del
 * borrador (`saveAgentSpecAction`) y se publica con «Guardar», que pasa la
 * puerta (39.1). Leer pide `agents:read`; comprobar, `agents:write` (39.12).
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const agentSchema = z.object({ ref, agent: uuid });

/** La forma de `model_policy` en `agent-spec.schema.json`. */
const policy = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("profile"), profile: z.enum(["auto", "economy", "balanced", "max"]) }),
  z.object({ kind: z.literal("pinned"), deployment: z.string().regex(/^[a-z0-9][a-z0-9._:/-]{2,120}$/) }),
]);

async function partner(perm: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, perm)) return null;
  return principal;
}

export async function modelQualityAction(raw: unknown): Promise<ActionResult<ModelQuality>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getModelQuality(body.ref, body.agent));
}

const checkSchema = agentSchema.extend({ policy });

/** «Comprobar la calidad» (39.9) → `202 {job_id}`. Se paga en «Construcción y pruebas». */
export async function checkModelQualityAction(raw: unknown): Promise<ActionResult<QualityCheckAccepted>> {
  const body = checkSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).checkModelQuality(body.ref, body.agent, body.policy));
}
