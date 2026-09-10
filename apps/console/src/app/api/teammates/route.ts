import { withPermission } from "../companion/_guard";

export const dynamic = "force-dynamic";

/**
 * Proxy del roster para la aplicación de escritorio (spec 003, R12.3). La
 * consola no tiene página para esto: es plumbing con la sesión de la persona.
 */
export async function GET(request: Request): Promise<Response> {
  const includeArchived = new URL(request.url).searchParams.get("include_archived") === "true";
  return withPermission("teammates:use", (b) => b.listTeammates(includeArchived));
}
