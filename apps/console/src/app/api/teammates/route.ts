import { z } from "zod";

import { badRequest, withPermission } from "../companion/_guard";

export const dynamic = "force-dynamic";

/** Los cinco interruptores del formulario. El catálogo lo deriva la API. */
const permissions = z.object({
  read: z.boolean(),
  write: z.boolean(),
  spend: z.boolean(),
  publish: z.boolean(),
  contact: z.boolean(),
});

/**
 * Lo que el formulario manda. **No hay `tool_names`** y no es un olvido: si
 * este esquema aceptara nombres de herramienta, la aplicación podría pedir una
 * que la plataforma no publica y el BFF la reenviaría (garantía 2). El límite
 * de 80 es el de la columna: rechazar aquí evita un 422 que llega después de
 * que la persona haya escrito el formulario entero.
 */
const create = z.object({
  name: z.string().min(1).max(80),
  job: z.string().min(1).max(80),
  model: z.string().min(1).max(200),
  permissions: permissions.optional(),
  local_exec: z.boolean().optional(),
});

/**
 * Proxy del roster para la aplicación de escritorio (spec 003, R12.3). La
 * consola no tiene página para esto: es plumbing con la sesión de la persona.
 */
export async function GET(request: Request): Promise<Response> {
  const includeArchived = new URL(request.url).searchParams.get("include_archived") === "true";
  return withPermission("teammates:use", (b) => b.listTeammates(includeArchived));
}

/** Crear un teammate (R2.1). Lo puede hacer cualquiera que use teammates. */
export async function POST(request: Request): Promise<Response> {
  const parsed = create.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest("Invalid teammate");
  return withPermission("teammates:use", (b) => b.createTeammate(parsed.data));
}
