"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type ClientAgent } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Spec 030 (R14): the agents of one client. Zod on the server, `can()`
 * before any call, and the API decides the rules (a unique name, a number
 * only for a published agent, never archiving the last one or one with
 * numbers) — its codes come back in `ActionResult.code` for the screen to
 * say in words.
 */

const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const id = z.string().uuid();
const name = z.string().trim().min(1).max(80);
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

async function writer() {
  const principal = await requirePrincipal();
  return can(principal.role, "agents:write") ? principal : null;
}

/** Every tab of the record shows the agents (selector, draft bar, numbers). */
function refresh(r: string) {
  revalidatePath(`/clients/${encodeURIComponent(r)}`, "layout");
}

const createSchema = z.object({
  ref,
  name,
  seed_template: z.string().min(1).max(64),
  placeholders: z.record(z.string(), z.string().max(2000)).default({}),
});
export async function createAgentAction(raw: unknown): Promise<ActionResult<ClientAgent>> {
  const body = createSchema.parse(raw);
  const principal = await writer();
  if (!principal) return forbidden;
  const res = await run(() =>
    backendFor(principal).createAgent(body.ref, {
      name: body.name,
      seed_template: body.seed_template,
      placeholders: body.placeholders,
    }),
  );
  if (res.ok) refresh(body.ref);
  return res;
}

const renameSchema = z.object({ ref, agent: id, name });
export async function renameAgentAction(raw: unknown): Promise<ActionResult<ClientAgent>> {
  const body = renameSchema.parse(raw);
  const principal = await writer();
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).updateAgent(body.ref, body.agent, { name: body.name }));
  if (res.ok) refresh(body.ref);
  return res;
}

const archiveSchema = z.object({ ref, agent: id });
export async function archiveAgentAction(raw: unknown): Promise<ActionResult<ClientAgent>> {
  const body = archiveSchema.parse(raw);
  const principal = await writer();
  if (!principal) return forbidden;
  const res = await run(() => backendFor(principal).updateAgent(body.ref, body.agent, { status: "archived" }));
  if (res.ok) refresh(body.ref);
  return res;
}

const assignSchema = z.object({ ref, channel: id, agent: id });
/** Which agent answers on a number from its next message on. */
export async function assignChannelAgentAction(raw: unknown): Promise<ActionResult<{ channel_id: string; agent_id: string }>> {
  const body = assignSchema.parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:write")) return forbidden;
  const res = await run(() => backendFor(principal).assignChannelAgent(body.ref, body.channel, body.agent));
  if (res.ok) refresh(body.ref);
  return res;
}
