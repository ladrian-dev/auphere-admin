import { z } from "zod";

import { badRequest, withCompanion } from "../../_guard";

export const dynamic = "force-dynamic";

/**
 * Stop. **This is the only thing that cancels a run.**
 *
 * Aborting the `fetch` of the stream tears down this *view* of the run and
 * nothing else — the work lives on AWS. The Ably write-up on resumable
 * streams names this exact trap (`stop()` and resumable streams are not
 * compatible out of the box); an explicit cancellation endpoint is what it
 * says to build, and the drawer's Stop button calls it.
 */
export async function DELETE(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  if (!z.string().uuid().safeParse(id).success) return badRequest("Invalid run");
  return withCompanion(async (b) => {
    await b.cancelCompanionRun(id);
    return null;
  });
}
