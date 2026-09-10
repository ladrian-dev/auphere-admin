import { z } from "zod";

import { badRequest, withPermission } from "../../../../companion/_guard";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

export async function POST(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return badRequest("Invalid task");
  return withPermission("teammates:use", (b) => b.cancelTeammateTask(p.data.id));
}
