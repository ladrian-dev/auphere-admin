"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type AgentVersion, type Client, type ClientCreated } from "@/lib/backend";
import { requirePrincipal } from "@/lib/principal";

/**
 * Server Actions for the clients area. Every input is Zod-validated on
 * the server (CP-32); every call goes to the API with a fresh principal
 * token — the API is what decides.
 */

const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);

const createSchema = z.object({
  external_client_ref: ref,
  name: z.string().min(1).max(255),
  timezone: z.string().min(1).max(64),
});
export async function createClientAction(raw: unknown): Promise<ActionResult<ClientCreated>> {
  const body = createSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).createClient(body));
  if (res.ok) revalidatePath("/clients");
  return res;
}

const updateSchema = z.object({ ref, name: z.string().min(1).max(255).optional(), timezone: z.string().min(1).max(64).optional() });
export async function updateClientAction(raw: unknown): Promise<ActionResult<Client>> {
  const { ref: r, ...body } = updateSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).updateClient(r, body));
  if (res.ok) revalidatePath(`/clients/${r}`);
  return res;
}

const statusSchema = z.object({ ref, status: z.enum(["active", "paused", "archived"]) });
export async function setClientStatusAction(raw: unknown): Promise<ActionResult<Client>> {
  const { ref: r, status } = statusSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).setClientStatus(r, status));
  if (res.ok) {
    revalidatePath(`/clients/${r}`);
    revalidatePath("/clients");
  }
  return res;
}

const deleteSchema = z.object({ ref, confirm_name: z.string().min(1).max(255) });
export async function deleteClientAction(raw: unknown): Promise<ActionResult<null>> {
  const { ref: r, confirm_name } = deleteSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).deleteClient(r, confirm_name));
  if (res.ok) revalidatePath("/clients");
  return res;
}

const draftSchema = z.object({ ref, system_prompt: z.string().min(1).max(200_000) });
export async function stageAgentAction(raw: unknown): Promise<ActionResult<AgentVersion>> {
  const { ref: r, system_prompt } = draftSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).stageAgentVersion(r, { system_prompt }));
  if (res.ok) revalidatePath(`/clients/${r}/agent`);
  return res;
}

const versionSchema = z.object({ ref, version: z.number().int().positive() });
export async function publishAgentAction(raw: unknown): Promise<ActionResult<AgentVersion>> {
  const { ref: r, version } = versionSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).publishAgentVersion(r, version));
  if (res.ok) revalidatePath(`/clients/${r}`);
  return res;
}
export async function rollbackAgentAction(raw: unknown): Promise<ActionResult<AgentVersion>> {
  const { ref: r, version } = versionSchema.parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).rollbackAgentVersion(r, version));
  if (res.ok) revalidatePath(`/clients/${r}`);
  return res;
}
