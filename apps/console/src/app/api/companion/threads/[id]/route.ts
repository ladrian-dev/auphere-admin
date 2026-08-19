import { z } from "zod";

import { badRequest, readJson, withCompanion } from "../../_guard";

export const dynamic = "force-dynamic";

const patchBody = z.object({
  title: z.string().min(1).max(200).optional(),
  archived: z.boolean().optional(),
  // Consult vs Build is an act of the USER, never of the model (§4.2).
  mode: z.enum(["consult", "build"]).optional(),
});

export async function PATCH(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const { id } = await ctx.params;
  const body = patchBody.safeParse(await readJson(request));
  if (!body.success || !z.string().uuid().safeParse(id).success) return badRequest("Invalid thread update");
  return withCompanion((b) => b.patchCompanionThread(id, body.data));
}
