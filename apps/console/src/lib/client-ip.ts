/**
 * La IP del visitante, para que la API pueda limitar por IP de verdad.
 *
 * **Por qué existe esto.** El navegador nunca habla con la API: habla con este
 * BFF (ADR-032). Así que la API veía siempre la IP de salida de Vercel, y el
 * cubo de ritmo «por IP» del login era en realidad un único cubo global. Con
 * un formulario de alta abierto eso deja de ser un detalle.
 *
 * **Por qué aquí sí se lee `x-forwarded-for`, y en la API no.** Aquí la pone
 * la plataforma delante de este proceso y el cliente no la controla. La API,
 * en cambio, es alcanzable por cualquiera que llegue a ella: allí una
 * `x-forwarded-for` no prueba nada, y por eso sólo acepta la cabecera propia
 * que este módulo rellena, dentro de una petición ya firmada con el token de
 * servicio.
 *
 * Si no se conoce la IP **no se inventa nada**: se omite la cabecera y la API
 * cae a su cubo único, que tiene nombre propio y se ve.
 */

/** El nombre tiene que coincidir con `core/client_ip.py` en la API. */
export const CLIENT_IP_HEADER = "X-Nexus-Client-IP";

/**
 * El primer valor de `x-forwarded-for` es el cliente; el resto son proxies.
 * `x-real-ip` es el respaldo de algunos despliegues.
 */
export function clientIpFrom(incoming: {
  get(name: string): string | null | undefined;
}): string | null {
  const forwarded = incoming.get("x-forwarded-for");
  const first = forwarded?.split(",")[0]?.trim();
  if (first) return first;
  const real = incoming.get("x-real-ip")?.trim();
  return real || null;
}

/** La cabecera lista para mezclar, o nada si no se sabe. */
export function clientIpHeader(incoming: {
  get(name: string): string | null | undefined;
}): Record<string, string> {
  const ip = clientIpFrom(incoming);
  return ip ? { [CLIENT_IP_HEADER]: ip } : {};
}
