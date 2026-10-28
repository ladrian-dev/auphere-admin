"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type {
  AgentConversationPage,
  AgentPerformance,
  ImprovementAccepted,
  ImprovementDiscarded,
  Improvements,
} from "@/lib/backend/agent-improve-types";
import { can, requirePrincipal, type Permission } from "@/lib/principal";

/**
 * Spec 047 (T174; requisitos 51 y 52.2) — Rendimiento y Mejoras de un agente.
 * Leer el rendimiento y las mejoras pide `agents:read`; la lista de
 * conversaciones, `conversations:read` (solo metadatos, nunca un mensaje);
 * aceptar y descartar, `agents:write`. Aceptar lleva el cambio y su prueba al
 * borrador sin publicar nada: «Guardar» pasa la puerta como cualquier cambio.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const agentSchema = z.object({ ref, agent: uuid });

async function partner(permission: Permission) {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

export async function performanceAction(raw: unknown): Promise<ActionResult<AgentPerformance>> {
  const p = agentSchema.extend({ days: z.number().int().min(1).max(90) }).parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentPerformance(p.ref, p.agent, p.days));
}

export async function conversationsAction(raw: unknown): Promise<ActionResult<AgentConversationPage>> {
  const p = agentSchema.extend({ cursor: z.string().min(1).max(200).optional() }).parse(raw);
  const principal = await partner("conversations:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).listAgentConversations(p.ref, p.agent, p.cursor));
}

export async function improvementsAction(raw: unknown): Promise<ActionResult<Improvements>> {
  const p = agentSchema.parse(raw);
  const principal = await partner("agents:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).listImprovements(p.ref, p.agent));
}

export async function acceptImprovementAction(raw: unknown): Promise<ActionResult<ImprovementAccepted>> {
  const p = agentSchema.extend({ id: uuid }).parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).acceptImprovement(p.ref, p.agent, p.id));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(p.ref)}`, "layout");
  return res;
}

export async function discardImprovementAction(raw: unknown): Promise<ActionResult<ImprovementDiscarded>> {
  const p = agentSchema.extend({ id: uuid, reason: z.string().trim().min(3).max(300) }).parse(raw);
  const principal = await partner("agents:write");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).discardImprovement(p.ref, p.agent, p.id, p.reason));
}
