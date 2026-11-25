/**
 * Spec 078, requisito 4: adónde vuelve el operador después del login.
 *
 * `?from=` lo pone el middleware con una ruta del panel, pero cualquiera
 * puede escribir un enlace al login con otro valor. `//otro-sitio` o
 * `/\otro-sitio` empiezan por `/` y el navegador los lee como otro dominio,
 * así que no basta con mirar el primer carácter: se resuelve contra un origen
 * propio y solo vale si se queda en él.
 */
const ORIGIN = "https://panel.invalid";

export function safeRedirect(from: string | null | undefined, fallback = "/tenants"): string {
  if (!from || !from.startsWith("/")) return fallback;
  try {
    const url = new URL(from, ORIGIN);
    if (url.origin !== ORIGIN) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}
