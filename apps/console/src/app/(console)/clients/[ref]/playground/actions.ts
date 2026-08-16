"use server";

import { z } from "zod";

import { run, type ActionResult } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import type { PlaygroundBudget, PlaygroundRunStarted, PlaygroundThread } from "@/lib/backend/playground";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Server Actions of the playground (CP-16). Zod on the server, fresh
 * principal token per call; the API decides (cap → 429 surfaces as
 * `{ok:false,status:429}` and the UI switches to "cap reached").
 */
const ref = z.string().min(1).max(255).regex(/^[A-Za-z0-9._:-]+$/);
const uuid = z.string().uuid();

async function principalOrDeny() {
  const principal = await requirePrincipal();
  if (!can(principal.role, "playground:run")) return null;
  return principal;
}
const denied = { ok: false as const, status: 403, message: "Missing permission playground:run" };

const createSchema = z.object({ ref, title: z.string().trim().min(1).max(200).optional() });
export async function createThreadAction(raw: unknown): Promise<ActionResult<PlaygroundThread>> {
  const { ref: r, title } = createSchema.parse(raw);
  const principal = await principalOrDeny();
  if (!principal) return denied;
  return run(() => backendFor(principal).createPlaygroundThread(r, title ? { title } : {}));
}

const patchSchema = z.object({
  ref,
  thread_id: uuid,
  title: z.string().trim().min(1).max(200).optional(),
  archived: z.boolean().optional(),
});
export async function patchThreadAction(raw: unknown): Promise<ActionResult<PlaygroundThread>> {
  const { ref: r, thread_id, ...body } = patchSchema.parse(raw);
  const principal = await principalOrDeny();
  if (!principal) return denied;
  return run(() => backendFor(principal).patchPlaygroundThread(r, thread_id, body));
}

const listSchema = z.object({ ref, include_archived: z.boolean().optional() });
export async function listThreadsAction(raw: unknown): Promise<ActionResult<PlaygroundThread[]>> {
  const { ref: r, include_archived } = listSchema.parse(raw);
  const principal = await principalOrDeny();
  if (!principal) return denied;
  return run(() => backendFor(principal).listPlaygroundThreads(r, { include_archived }));
}

const runSchema = z.object({ ref, thread_id: uuid, prompt: z.string().min(1).max(4000) });
export async function startRunAction(raw: unknown): Promise<ActionResult<PlaygroundRunStarted>> {
  const { ref: r, thread_id, prompt } = runSchema.parse(raw);
  const principal = await principalOrDeny();
  if (!principal) return denied;
  return run(() => backendFor(principal).startPlaygroundRun(r, thread_id, prompt));
}

const cancelSchema = z.object({ ref, run_id: uuid });
export async function cancelRunAction(raw: unknown): Promise<ActionResult<null>> {
  const { ref: r, run_id } = cancelSchema.parse(raw);
  const principal = await principalOrDeny();
  if (!principal) return denied;
  return run(async () => {
    await backendFor(principal).cancelPlaygroundRun(r, run_id);
    return null;
  });
}

export async function getBudgetAction(): Promise<ActionResult<PlaygroundBudget>> {
  const principal = await principalOrDeny();
  if (!principal) return denied;
  return run(() => backendFor(principal).getPlaygroundBudget());
}
