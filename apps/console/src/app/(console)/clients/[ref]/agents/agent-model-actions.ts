"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { AgentModel } from "@/lib/backend/models";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 065 (T027; requisitos 2.3, 2.4 y 2.7) — Agente › Avanzado › Modelo:
 * leer el modelo del agente con lo que el partner puede elegir, y cambiarlo.
 *
 * Leer pide `agents:read`; cambiar, `agents:write` (2.4), comprobado aquí antes
 * de llamar a la API, que lo vuelve a comprobar. El cambio vale desde el
 * siguiente turno del agente, sin publicar versión (2.3). La consola siempre
 * manda un modelo: volver al modelo por defecto de Auphere no se ofrece (2.7),
 * así que `null` no pasa el esquema. Los códigos de la API (`unknown_model`,
 * `model_unavailable_for_agent`) vuelven tal cual en `code`.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const agentSchema = z.object({ ref, agent: uuid });
const setSchema = agentSchema.extend({ model_id: z.string().min(1).max(64) });

async function partner(permission: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

export async function agentModelAction(raw: unknown): Promise<ActionResult<AgentModel>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentModel(body.ref, body.agent));
}

export async function setAgentModelAction(raw: unknown): Promise<ActionResult<AgentModel>> {
  const body = setSchema.parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).setAgentModel(body.ref, body.agent, body.model_id));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}/agents/${encodeURIComponent(body.agent)}`);
  return res;
}
