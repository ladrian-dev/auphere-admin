import { z } from "zod";

import { badRequest, withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

const params = z.object({ id: z.string().uuid() });

const permissions = z.object({
  read: z.boolean(),
  write: z.boolean(),
  spend: z.boolean(),
  publish: z.boolean(),
  contact: z.boolean(),
});

/**
 * El parche. Todo opcional —se manda lo que cambió— y, como al crear, **sin
 * `tool_names`**: quien decide el catálogo es la API a partir de los
 * interruptores, no la pantalla.
 */
const patch = z
  .object({
    name: z.string().min(1).max(80).optional(),
    job: z.string().min(1).max(80).optional(),
    model: z.string().min(1).max(200).optional(),
    permissions: permissions.optional(),
    local_exec: z.boolean().optional(),
  })
  .refine((body) => Object.keys(body).length > 0, { message: "empty patch" });

/** Cambiar un teammate (R2.3). El siguiente turno usa el catálogo nuevo. */
export async function PATCH(request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return badRequest("Invalid teammate");
  const parsed = patch.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest("Invalid change");
  return withPermission("teammates:use", (b) => b.patchTeammate(p.data.id, parsed.data));
}

/** Archivar un teammate. **Nunca borra** (R2.6): sus hilos quedan legibles. */
export async function DELETE(_request: Request, ctx: { params: Promise<{ id: string }> }): Promise<Response> {
  const p = params.safeParse(await ctx.params);
  if (!p.success) return badRequest("Invalid teammate");
  return withPermission("teammates:use", (b) => b.archiveTeammate(p.data.id));
}
