"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { LiteAgent, LiteAgentChannel, LiteAgents } from "@/lib/backend/lite-agents";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Spec 047 (T168; requisitos 50.1, 50.2 y 27.6) — «Agentes» de la persona del
 * cliente: pausar y reanudar sus agentes y sus números. Zod aquí; la API vuelve
 * a validar, guarda quién y desde dónde (`lite_web`) y avisa al partner. Una
 * pausa del sistema (sin saldo, el tope) no la quita una persona: 409
 * `system_pause`. Con conversaciones en curso, pausar pide confirmación: 409
 * `confirm_required` con cuántas.
 */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const id = z.string().uuid();

async function agentsPrincipal() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok" || res.principal.kind !== "client") return null;
  return res.principal.modules.includes("agents") ? res.principal : null;
}

async function act<T>(fn: (api: ReturnType<typeof backendFor>) => Promise<T>): Promise<ActionResult<T>> {
  const principal = await agentsPrincipal();
  if (!principal) return forbidden;
  const res = await run(() => fn(backendFor(principal)));
  if (res.ok) revalidatePath("/agentes");
  return res;
}

export async function reloadAgentsAction(): Promise<ActionResult<LiteAgents>> {
  const principal = await agentsPrincipal();
  if (!principal) return forbidden;
  return run(() => backendFor(principal).liteAgents());
}

export async function pauseAgentAction(raw: unknown): Promise<ActionResult<LiteAgent>> {
  const p = z.object({ id, confirm: z.boolean() }).parse(raw);
  return act((api) => api.litePauseAgent(p.id, p.confirm));
}

export async function resumeAgentAction(raw: unknown): Promise<ActionResult<LiteAgent>> {
  const p = z.object({ id }).parse(raw);
  return act((api) => api.liteResumeAgent(p.id));
}

export async function pauseChannelAction(raw: unknown): Promise<ActionResult<LiteAgentChannel>> {
  const p = z.object({ id }).parse(raw);
  return act((api) => api.litePauseChannel(p.id));
}

export async function resumeChannelAction(raw: unknown): Promise<ActionResult<LiteAgentChannel>> {
  const p = z.object({ id }).parse(raw);
  return act((api) => api.liteResumeChannel(p.id));
}
