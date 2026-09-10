import { z } from "zod";

import { badRequest, withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

const body = z.object({
  // `null` = la preferencia global de esta persona.
  executable: z.string().regex(/^[A-Za-z0-9._+-]{1,128}$/).nullable(),
  mode: z.enum(["ask", "always", "never"]),
});

/** La preferencia de ejecución local de la persona, con el techo ya aplicado. */
export async function GET(): Promise<Response> {
  return withPermission("teammates:use", (b) => b.localExecPrefs());
}

export async function PUT(request: Request): Promise<Response> {
  const parsed = body.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest("Invalid preference");
  return withPermission("teammates:use", (b) => b.setLocalExecPref(parsed.data));
}
