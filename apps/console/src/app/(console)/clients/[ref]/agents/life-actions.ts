"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type ClientAgent } from "@/lib/backend";
import type { AgentHeader, CopilotAnswer, CopilotFixResult } from "@/lib/backend/agent-life-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historias 19 y 20, T124; historia 18, T099) — las acciones de la
 * cabecera de un agente (renombrar, pausar, reanudar, archivar con el destino de
 * cada número, restaurar y hacerlo agente por defecto) y del copiloto.
 *
 * `agents:write` para cambiar la vida del agente y para «Arreglar»; el copiloto
 * responde con `agents:read` (a quien solo lee, le explica, 19.5). La API decide
 * las reglas —la confirmación con conversaciones en curso, el destino de cada
 * número, el agente por defecto— y sus códigos vuelven en `code`.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const agentSchema = z.object({ ref, agent: uuid });

async function partner(permission: "agents:read" | "agents:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

/** El estado de un agente sale en la lista de clientes, la pestaña Agentes y su cabecera. */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

async function write<T>(r: string, fn: (api: ReturnType<typeof backendFor>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => fn(backendFor(principal)));
  if (res.ok) refresh(r);
  return res;
}

export async function agentHeaderAction(raw: unknown): Promise<ActionResult<AgentHeader>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentHeader(body.ref, body.agent));
}

const renameSchema = agentSchema.extend({ name: z.string().trim().min(1).max(40) });

/** Renombrar, también el agente por defecto (26.4). */
export async function renameAgentLifeAction(raw: unknown): Promise<ActionResult<ClientAgent>> {
  const body = renameSchema.parse(raw);
  return write(body.ref, (api) => api.updateAgent(body.ref, body.agent, { name: body.name }));
}

const pauseSchema = agentSchema.extend({ confirm: z.boolean().optional(), note: z.string().trim().max(300).optional() });

/** Pausar: `409 confirm_required` con las conversaciones en curso si no se confirmó (27.8). */
export async function pauseAgentAction(raw: unknown): Promise<ActionResult<AgentHeader>> {
  const body = pauseSchema.parse(raw);
  return write(body.ref, (api) =>
    api.pauseAgent(body.ref, body.agent, { ...(body.confirm ? { confirm: true } : {}), ...(body.note ? { note: body.note } : {}) }),
  );
}

/** Reanudar: vuelve el estado de antes de la pausa (27.3). */
export async function resumeAgentAction(raw: unknown): Promise<ActionResult<AgentHeader>> {
  const body = agentSchema.parse(raw);
  return write(body.ref, (api) => api.resumeAgent(body.ref, body.agent));
}

const archiveSchema = agentSchema.extend({
  channels: z.array(z.object({ channel_id: uuid, to: z.union([uuid, z.literal("pause")]) })).max(50),
});

/** Archivar con el destino de cada número: otro agente o «pause» (28.1). */
export async function archiveAgentWithAction(raw: unknown): Promise<ActionResult<AgentHeader>> {
  const body = archiveSchema.parse(raw);
  return write(body.ref, (api) => api.archiveAgentWith(body.ref, body.agent, body.channels));
}

/** Restaurar: vuelve en pausa (28.2). */
export async function restoreAgentAction(raw: unknown): Promise<ActionResult<AgentHeader>> {
  const body = agentSchema.parse(raw);
  return write(body.ref, (api) => api.restoreAgent(body.ref, body.agent));
}

/** El agente por defecto, de una vez (26.2). */
export async function setDefaultAgentAction(raw: unknown): Promise<ActionResult<AgentHeader>> {
  const body = agentSchema.parse(raw);
  return write(body.ref, (api) => api.setDefaultAgent(body.ref, body.agent));
}

// ── el copiloto (requisito 19) ──────────────────────────────────────────────

const copilotSchema = agentSchema.extend({
  message: z.string().trim().max(1000),
  context: z
    .object({
      answer: z.string().max(4000).optional(),
      actions: z.array(z.object({ tool: z.string().max(160), phrase: z.string().max(500) })).max(20).optional(),
      test_id: uuid.optional(),
    })
    .optional(),
});

/** Preguntar al copiloto: citas con enlace y, a quien puede escribir, propuestas. */
export async function copilotAction(raw: unknown): Promise<ActionResult<CopilotAnswer>> {
  const body = copilotSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).askCopilot(body.ref, body.agent, body.message, body.context));
}

const fixSchema = agentSchema.extend({ test: uuid, scope: z.enum(["business", "agent"]), value: z.string().trim().min(1).max(2000) });

/** «Arreglar» un dato donde la persona dijo: la ficha o solo este agente (19.4). */
export async function copilotFixAction(raw: unknown): Promise<ActionResult<CopilotFixResult>> {
  const body = fixSchema.parse(raw);
  const res = await write(body.ref, (api) => api.copilotFix(body.ref, body.agent, { test_id: body.test, scope: body.scope, value: body.value }));
  if (res.ok && body.scope === "business") revalidatePath(`/clients/${encodeURIComponent(body.ref)}/business`);
  return res;
}
