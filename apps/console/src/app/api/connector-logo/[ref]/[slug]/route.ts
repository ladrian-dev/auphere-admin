import { backendFor } from "@/lib/backend";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * El logotipo de un conector, servido desde nuestro propio origen.
 *
 * **Por qué existe.** El catálogo trae la URL del logotipo del proveedor
 * —`agendapro.com/favicon.ico`, el SVG de WhatsApp en Wikimedia— y la tarjeta
 * las pintaba directamente. Ninguna cargaba nunca: la consola publica
 * `img-src 'self' data: blob:`, así que el navegador las bloqueaba todas y
 * dibujaba el icono de imagen rota. Se veía en Conectores desde el primer día.
 *
 * Abrir `img-src` a esos dominios habría sido más rápido y peor: el catálogo
 * admite **cualquier** dominio, así que la única regla que los cubre a todos es
 * `img-src *`, que es no tener regla. Y cada tarjeta le pediría una imagen a
 * Meta o a WordPress desde el navegador del partner, contándoles qué conectores
 * mira.
 *
 * **Por qué por `slug` y no por URL.** Una ruta que acepte una URL y la
 * descargue es una puerta para pedir lo que sea desde nuestro servidor. Aquí la
 * URL **no la elige quien llama**: se busca en el catálogo del propio cliente,
 * que es de donde salía antes.
 *
 * Sin logotipo en el catálogo → 404, y la tarjeta cae en su inicial sobre un
 * cuadro tintado, que es el respaldo que ya tenía.
 */

/** Lo que aceptamos devolver. Un catálogo no puede convertirse en una vía para
 *  servir cualquier cosa desde nuestro dominio. */
const IMAGENES = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "image/svg+xml",
  "image/x-icon",
  "image/vnd.microsoft.icon",
]);

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ ref: string; slug: string }> },
): Promise<Response> {
  const { ref, slug } = await params;
  const sesion = await resolvePrincipal();
  if (sesion.kind !== "ok") return new Response(null, { status: 401 });

  let url: string | null = null;
  try {
    const catalogo = await backendFor(sesion.principal).listConnectors(decodeURIComponent(ref));
    url = catalogo.find((c) => c.slug === decodeURIComponent(slug))?.logo_url ?? null;
  } catch {
    return new Response(null, { status: 502 });
  }
  if (!url) return new Response(null, { status: 404 });

  try {
    const remoto = await fetch(url, {
      signal: AbortSignal.timeout(5_000),
      // Wikimedia —de donde sale el logotipo de WhatsApp en el catálogo—
      // devuelve **403 a quien no se identifica**, y el `fetch` del servidor
      // no manda agente por su cuenta. Sin esta línea, la imagen no llega y
      // la tarjeta cae en su icono de respaldo, que es exactamente lo que
      // pasó en staging.
      headers: { "user-agent": "AuphereConsole/1.0 (+https://auphere.com)" },
    });
    const tipo = (remoto.headers.get("content-type") ?? "").split(";")[0]!.trim().toLowerCase();
    if (!remoto.ok || !IMAGENES.has(tipo)) return new Response(null, { status: 404 });
    return new Response(remoto.body, {
      headers: {
        "content-type": tipo,
        // Un logotipo cambia una vez cada varios años. `private` porque la
        // respuesta viaja detrás de una sesión, aunque la imagen no sea de
        // nadie en particular.
        "cache-control": "private, max-age=86400",
      },
    });
  } catch {
    // Un proveedor caído no puede romper la pantalla de Conectores: la tarjeta
    // enseña su inicial y sigue funcionando.
    return new Response(null, { status: 404 });
  }
}
