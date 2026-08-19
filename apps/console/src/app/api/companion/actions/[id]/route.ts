import { z } from "zod";

import { badRequest, withCompanion } from "../../_guard";

export const dynamic = "force-dynamic";

/**
 * Read one proposed action (§5.1). This exists for the PARTIAL state:
 * reloading with a confirmation pending has to paint the card without
 * depending on the Redis run log still being alive.
 *
 * **Nothing serves this endpoint yet** — CO-04 builds it in parallel.
 */
export async function GET(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  if (!z.string().uuid().safeParse(id).success) return badRequest("Invalid action");
  return withCompanion((b) => b.getCompanionAction(id));
}
