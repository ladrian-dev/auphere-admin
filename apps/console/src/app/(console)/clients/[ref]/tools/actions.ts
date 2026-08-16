"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { TOOL_MODES, type ConnectorOut, type ConnectorSyncOut, type ConsentOut, type ToolModeOut, type ToolsSaved } from "@/lib/backend/agent-tools";
import { can, requirePrincipal } from "@/lib/principal";

/** Server Actions of lane `agent-tools` — tools whitelist, per-tool mode and
 *  connectors (CP-13). All writes gated by `agents:write`. */

const ref = z.string().min(1).max(255);
const toolName = z.string().min(1).max(200);
const slug = z.string().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/);

function forbidden<T>(): ActionResult<T> {
  return { ok: false, status: 403, message: "forbidden" };
}
const toolsPath = (r: string) => `/clients/${encodeURIComponent(r)}/tools`;

export async function saveToolsAction(raw: unknown): Promise<ActionResult<ToolsSaved>> {
  const body = z.object({ ref, tools: z.array(toolName).max(200) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).putTools(body.ref, body.tools));
  if (res.ok) revalidatePath(`/clients/${encodeURIComponent(body.ref)}`, "layout");
  return res;
}

export async function setToolModeAction(raw: unknown): Promise<ActionResult<ToolModeOut>> {
  const body = z.object({ ref, tool: toolName, mode: z.enum(TOOL_MODES) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).putToolMode(body.ref, body.tool, body.mode));
  if (res.ok) revalidatePath(toolsPath(body.ref));
  return res;
}

export async function resetToolModeAction(raw: unknown): Promise<ActionResult<null>> {
  const body = z.object({ ref, tool: toolName }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).deleteToolMode(body.ref, body.tool));
  if (res.ok) revalidatePath(toolsPath(body.ref));
  return res;
}

export async function startConsentAction(raw: unknown): Promise<ActionResult<ConsentOut>> {
  const body = z.object({ ref, slug }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).startConsent(body.ref, body.slug));
  if (res.ok) revalidatePath(toolsPath(body.ref));
  return res;
}

export async function syncConnectorAction(raw: unknown): Promise<ActionResult<ConnectorSyncOut>> {
  const body = z.object({ ref, slug }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).syncConnector(body.ref, body.slug));
  if (res.ok) revalidatePath(toolsPath(body.ref));
  return res;
}

export async function connectorStatusAction(raw: unknown): Promise<ActionResult<ConnectorOut>> {
  const body = z.object({ ref, slug, op: z.enum(["pause", "resume", "disconnect"]) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const api = backendFor(principal);
  const fn = body.op === "pause" ? api.pauseConnector : body.op === "resume" ? api.resumeConnector : api.disconnectConnector;
  const res = await run(() => fn(body.ref, body.slug));
  if (res.ok) revalidatePath(toolsPath(body.ref));
  return res;
}

export async function connectApiKeyAction(raw: unknown): Promise<ActionResult<ConnectorOut>> {
  const body = z
    .object({
      ref,
      slug,
      secrets: z.record(z.string().min(1).max(64), z.string().min(1).max(4096)).refine((s) => Object.keys(s).length >= 1 && Object.keys(s).length <= 20),
      endpoint_meta: z.record(z.string().min(1).max(64), z.string().max(2048)).refine((m) => Object.keys(m).length <= 20),
    })
    .parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:write")) return forbidden();
  const res = await run(() => backendFor(principal).connectApiKey(body.ref, body.slug, { secrets: body.secrets, endpoint_meta: body.endpoint_meta }));
  if (res.ok) revalidatePath(toolsPath(body.ref));
  return res;
}
