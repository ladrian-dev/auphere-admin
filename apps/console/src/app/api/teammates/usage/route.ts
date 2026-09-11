import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

/**
 * El consumo que pinta Cuenta en la aplicación (spec 003, R8.1). El `budget`
 * que devuelve es el mismo objeto que `/api/companion/budget`: un medidor.
 */
export async function GET(): Promise<Response> {
  return withPermission("teammates:use", (b) => b.teammatesUsage());
}
