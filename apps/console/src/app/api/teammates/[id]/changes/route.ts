import { z } from "zod";

import { badRequest, withPermission } from "../../../companion/_guard";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

/**
 * Las notas de «este teammate cambió» (R2.4). El hilo las intercala con sus
 * runs al cargar, así que quien no estaba mirando ve el cambio donde ocurrió.
 */
export async function GET(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return badRequest("Invalid teammate");
  return withPermission("teammates:use", (b) => b.teammateChanges(p.data.id));
}
