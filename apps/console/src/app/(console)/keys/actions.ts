"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type ApiKey, type ApiKeyCreated } from "@/lib/backend";
import { requirePrincipal } from "@/lib/principal";

const id = z.string().uuid();
const scope = z.enum(["provision", "broadcasts", "widget_sessions"]);

export async function createKeyAction(raw: unknown): Promise<ActionResult<ApiKeyCreated>> {
  const body = z.object({ type: z.enum(["live", "test"]), scopes: z.array(scope).min(1) }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).createKey(body));
  if (res.ok) revalidatePath("/keys");
  return res;
}
export async function rotateKeyAction(raw: unknown): Promise<ActionResult<ApiKeyCreated>> {
  const { id: keyId } = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).rotateKey(keyId, 24));
  if (res.ok) revalidatePath("/keys");
  return res;
}
export async function revokeKeyAction(raw: unknown): Promise<ActionResult<ApiKey>> {
  const { id: keyId } = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  const res = await run(() => backendFor(principal).revokeKey(keyId));
  if (res.ok) revalidatePath("/keys");
  return res;
}
