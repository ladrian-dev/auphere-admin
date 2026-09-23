"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor, type ApiKey, type ApiKeyCreated } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/** Spec 016 (R8.1): the console says «no puedes» itself — the same permission the API enforces (`keys:manage`). */
const forbidden = { ok: false as const, status: 403, message: "forbidden" };

const id = z.string().uuid();
const scope = z.enum(["provision", "broadcasts"]);

export async function createKeyAction(raw: unknown): Promise<ActionResult<ApiKeyCreated>> {
  const body = z.object({ type: z.enum(["live", "test"]), scopes: z.array(scope).min(1) }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "keys:manage")) return forbidden;
  const res = await run(() => backendFor(principal).createKey(body));
  if (res.ok) revalidatePath("/keys");
  return res;
}
export async function rotateKeyAction(raw: unknown): Promise<ActionResult<ApiKeyCreated>> {
  const { id: keyId } = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "keys:manage")) return forbidden;
  const res = await run(() => backendFor(principal).rotateKey(keyId, 24));
  if (res.ok) revalidatePath("/keys");
  return res;
}
export async function revokeKeyAction(raw: unknown): Promise<ActionResult<ApiKey>> {
  const { id: keyId } = z.object({ id }).parse(raw);
  const principal = await requirePrincipal();
  if (!can(principal.role, "keys:manage")) return forbidden;
  const res = await run(() => backendFor(principal).revokeKey(keyId));
  if (res.ok) revalidatePath("/keys");
  return res;
}
