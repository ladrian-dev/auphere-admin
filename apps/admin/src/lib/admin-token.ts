import "server-only";

/**
 * Spec 078, requisito 5: el token de servicio con el que el panel habla con la
 * API. Es el único sitio que lo lee.
 *
 * En desarrollo vale el de siempre. En producción, sin token o con el de
 * desarrollo, falla con un mensaje que dice qué falta: la API ya se niega a
 * arrancar así, y un panel que solo recibiera 401 no diría por qué. Se lee al
 * hacer cada llamada, no al cargar el módulo, para que `next build` no lo
 * necesite.
 */
const DEV_TOKEN = "dev-admin-token-change-me";

export function adminToken(): string {
  const token = process.env.NEXUS_ADMIN_TOKEN;
  if (token && !token.includes("change-me")) return token;
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "NEXUS_ADMIN_TOKEN falta o es el de desarrollo: en producción el panel no llama a la API sin el token de servicio de su entorno.",
    );
  }
  return token ?? DEV_TOKEN;
}
