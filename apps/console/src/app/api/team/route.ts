import { withPermission } from "../companion/_guard";

export const dynamic = "force-dynamic";

/**
 * El equipo, para la pantalla de Cuenta de la aplicación (R8.2). **Solo
 * lectura**: invitar, cambiar roles y dar de baja son de la consola, que ya
 * tiene su página con los permisos que eso exige.
 */
export async function GET(): Promise<Response> {
  return withPermission("team:read", (b) => b.team());
}
