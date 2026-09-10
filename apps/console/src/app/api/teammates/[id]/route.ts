import { z } from "zod";

import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

/** Archivar un teammate. **Nunca borra** (R2.6): sus hilos quedan legibles. */
export async function DELETE(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return new Response(JSON.stringify({ detail: "Invalid teammate" }), { status: 422 });
  return withPermission("teammates:use", (b) => b.archiveTeammate(p.data.id));
}
