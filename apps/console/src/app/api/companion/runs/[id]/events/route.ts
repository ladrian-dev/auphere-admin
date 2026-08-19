import { z } from "zod";

import { badRequest, withCompanion } from "../../../_guard";

export const dynamic = "force-dynamic";

const query = z.object({ since_seq: z.coerce.number().int().min(0).default(0) });

/**
 * REST history of one run. Half of the reconnection pattern of correction
 * C1: open the stream, list the history, drop what you already have by
 * `(run_id, seq)`, then follow live. A stream alone tells you there is a
 * hole but not where to fill it from.
 */
export async function GET(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  const q = query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
  if (!q.success || !z.string().uuid().safeParse(id).success) return badRequest("Invalid history request");
  return withCompanion((b) => b.getCompanionRunEvents(id, q.data.since_seq));
}
