import { z } from "zod";

import { badRequest, readJson, withCompanion } from "../../../_guard";

export const dynamic = "force-dynamic";

const startBody = z.object({
  prompt: z.string().min(1).max(8000),
  // Where the user is standing. Travels to the model as a mid-conversation
  // system message, never inside the cached system prefix (C4). Bounded so
  // a crafted client cannot push a novel through it.
  page_context: z
    .object({
      route: z.string().max(512),
      client_ref: z.string().max(255).nullable(),
      tab: z.string().max(128).nullable(),
      selection: z.string().max(512).nullable(),
    })
    .nullable()
    .optional(),
});

/**
 * The runs of this thread, ascending by `started_at` (§5.2, contract v1.1).
 *
 * This is what lets the drawer rebuild a whole thread on a machine that has
 * never seen it — which is the point of `?companion=<thread>` being
 * shareable. Before this endpoint the index could only live in
 * `localStorage`, and a shared link opened elsewhere showed an empty
 * conversation.
 *
 * **Nothing serves this endpoint yet** — CO-04 builds it in parallel.
 */
export async function GET(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  if (!z.string().uuid().safeParse(id).success) return badRequest("Invalid thread");
  return withCompanion((b) => b.listCompanionThreadRuns(id));
}

/**
 * 202 and back immediately: the run keeps going on AWS whatever happens to
 * this browser (correction C1). The caller then opens the stream.
 */
export async function POST(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  const body = startBody.safeParse(await readJson(request));
  if (!body.success || !z.string().uuid().safeParse(id).success) return badRequest("Invalid run request");
  return withCompanion((b) => b.startCompanionRun(id, body.data.prompt, body.data.page_context ?? undefined));
}
