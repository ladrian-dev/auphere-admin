import { withPermission } from "../../companion/_guard";

export const dynamic = "force-dynamic";

/**
 * El plan y lo que admite, para la aplicación de escritorio — spec 010, R9.
 *
 * **Solo lectura.** Contratar, cambiar de plan y comprar saldo siguen ocurriendo
 * en el navegador, por el traspaso del R9.4: la aplicación no pide ni enseña
 * datos de tarjeta en ningún caso (R9.10).
 *
 * Con `billing:read`, que es el permiso que la consola ya exige para esta misma
 * lectura: quien no lo tiene no ve el plan y se le dice a quién pedírselo, en
 * vez de ofrecerle una acción que va a rebotar (R9.2).
 */
export async function GET(): Promise<Response> {
  return withPermission("billing:read", (b) => b.membership());
}
