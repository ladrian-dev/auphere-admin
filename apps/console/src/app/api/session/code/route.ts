import { withPrincipal } from "../../companion/_guard";

export const dynamic = "force-dynamic";

/**
 * Emitir el código que lleva esta sesión a la aplicación de escritorio
 * (spec 009, R3.1).
 *
 * **`withPrincipal` y no `withPermission`**: llevarse la propia sesión a la
 * propia aplicación no es una capacidad que un rol conceda o niegue. Es de la
 * persona, y basta con que haya iniciado sesión.
 *
 * Esta ruta **no** es pública: quien la llama ya está dentro. La pública es la
 * del canje, que es donde llega alguien que todavía no tiene sesión.
 */
export async function POST(): Promise<Response> {
  return withPrincipal((b) => b.issueSessionCode());
}
