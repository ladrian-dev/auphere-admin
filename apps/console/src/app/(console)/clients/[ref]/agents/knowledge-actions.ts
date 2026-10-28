"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { TEACH_MAX_CHARS, uploadAgentKnowledgeFile, type AgentKnowledge, type KnowledgeSource } from "@/lib/backend/agent-knowledge";
import { KNOWLEDGE_MAX_UPLOAD_BYTES } from "@/lib/backend/agent-tools-types";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 047 (historia 22, T134) — la pestaña Conocimiento de un agente: sus
 * fuentes propias (archivo o web solo para él), quitar con 10 minutos para
 * deshacer, y «Enseñar» con el alcance que elige la persona (37.3). También
 * deshacer «Eliminar» en la capa del negocio.
 *
 * `knowledge:read` para leer, `knowledge:write` para todo lo demás. El texto de
 * las fuentes nunca pasa por aquí: los archivos van tal cual a la API.
 */

const forbidden = { ok: false as const, status: 403, message: "forbidden" };
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();
const agentSchema = z.object({ ref, agent: uuid });
const docSchema = agentSchema.extend({ doc: uuid });

async function partner(permission: "knowledge:read" | "knowledge:write") {
  const principal = await requirePrincipal();
  if (principal.kind !== "partner" || !can(principal.role, permission)) return null;
  return principal;
}

/** La pantalla del agente, y Negocio cuando cambia la capa del negocio. */
function refresh(r: string, agentId: string, business = false) {
  revalidatePath(`/clients/${encodeURIComponent(r)}/agents/${encodeURIComponent(agentId)}`);
  if (business) revalidatePath(`/clients/${encodeURIComponent(r)}/knowledge`);
}

export async function agentKnowledgeAction(raw: unknown): Promise<ActionResult<AgentKnowledge>> {
  const body = agentSchema.parse(raw);
  const principal = await partner("knowledge:read");
  if (!principal) return forbidden;
  return run(() => backendFor(principal).getAgentKnowledge(body.ref, body.agent));
}

/** Multipart: `ref`, `agent`, `file` y `title` opcional. El tamaño se vuelve a mirar en la API (413). */
export async function uploadAgentKnowledgeAction(formData: FormData): Promise<ActionResult<KnowledgeSource>> {
  const ids = agentSchema.parse({ ref: formData.get("ref"), agent: formData.get("agent") });
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, status: 422, message: "file required" };
  if (file.size > KNOWLEDGE_MAX_UPLOAD_BYTES) return { ok: false, status: 413, message: "file exceeds 10 MB" };
  const title = z.string().max(255).optional().parse(formData.get("title")?.toString().trim() || undefined);
  const principal = await partner("knowledge:write");
  if (!principal) return forbidden;
  const upstream = new FormData();
  upstream.set("file", file, file.name);
  if (title) upstream.set("title", title);
  const res = await run(() => uploadAgentKnowledgeFile(principal, ids.ref, ids.agent, upstream));
  if (res.ok) refresh(ids.ref, ids.agent);
  return res;
}

const urlSchema = agentSchema.extend({
  url: z.string().trim().min(8).max(2048).regex(/^https?:\/\//),
  title: z.string().trim().max(255).optional(),
});

export async function addAgentKnowledgeUrlAction(raw: unknown): Promise<ActionResult<KnowledgeSource>> {
  const body = urlSchema.parse(raw);
  const principal = await partner("knowledge:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).addAgentKnowledgeUrl(body.ref, body.agent, { url: body.url, ...(body.title ? { title: body.title } : {}) }));
  if (res.ok) refresh(body.ref, body.agent);
  return res;
}

/** Quitar: deja de usarse desde el siguiente mensaje; se restaura durante 10 minutos (12.2). */
export async function removeAgentKnowledgeAction(raw: unknown): Promise<ActionResult<null>> {
  const body = docSchema.parse(raw);
  const principal = await partner("knowledge:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).removeAgentKnowledge(body.ref, body.agent, body.doc));
  if (res.ok) refresh(body.ref, body.agent);
  return res;
}

/** Deshacer «Quitar»: `409 undo_window_closed` pasados 10 minutos. */
export async function restoreAgentKnowledgeAction(raw: unknown): Promise<ActionResult<KnowledgeSource>> {
  const body = docSchema.parse(raw);
  const principal = await partner("knowledge:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).restoreAgentKnowledge(body.ref, body.agent, body.doc));
  if (res.ok) refresh(body.ref, body.agent);
  return res;
}

const teachSchema = agentSchema.extend({
  text: z.string().trim().min(1).max(TEACH_MAX_CHARS),
  scope: z.enum(["business", "agent"]),
});

/** «Enseñar» con el alcance que eligió la persona (37.3); sin alcance no se manda. */
export async function teachAction(raw: unknown): Promise<ActionResult<KnowledgeSource>> {
  const body = teachSchema.parse(raw);
  const principal = await partner("knowledge:write");
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).teachAgent(body.ref, body.agent, { text: body.text, scope: body.scope }));
  if (res.ok) refresh(body.ref, body.agent, body.scope === "business");
  return res;
}

const layerDocSchema = z.object({ ref, agent: uuid, doc: uuid, scope: z.enum(["business", "agent"]) });

/**
 * Deshacer «Enseñar»: quitar la fuente que creó, en su capa. Se puede volver a
 * recuperar durante 10 minutos.
 */
export async function forgetTaughtAction(raw: unknown): Promise<ActionResult<null>> {
  const body = layerDocSchema.parse(raw);
  const principal = await partner("knowledge:write");
  if (!principal) return forbidden;
  const api = backendFor(principal);
  const res = await run(() => (body.scope === "agent" ? api.removeAgentKnowledge(body.ref, body.agent, body.doc) : api.deleteKnowledge(body.ref, body.doc)));
  if (res.ok) refresh(body.ref, body.agent, body.scope === "business");
  return res;
}
