import { backendFor } from "@/lib/backend";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * El logotipo de la aplicación de un canal, servido desde nuestro origen.
 *
 * Gemela de `/api/connector-logo/…` y por la misma razón: la consola publica
 * `img-src 'self' data: blob:`, así que una imagen de otro dominio no carga
 * nunca. Y por la misma cautela: **la URL no la elige quien llama**, se busca
 * en los canales de ese cliente.
 *
 * Existe aparte porque WhatsApp **no está** en el catálogo que la consola ve:
 * los conectores «solo canal» se filtran de ahí —no se conectan desde
 * Conectores, se conectan desde Canales— así que su logotipo viaja con el
 * canal.
 */
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
  { params }: { params: Promise<{ ref: string; channelId: string }> },
): Promise<Response> {
  const { ref, channelId } = await params;
  const sesion = await resolvePrincipal();
  if (sesion.kind !== "ok") return new Response(null, { status: 401 });

  let url: string | null = null;
  try {
    const overview = await backendFor(sesion.principal).channelsOverview(decodeURIComponent(ref));
    url = overview.channels.find((c) => c.id === decodeURIComponent(channelId))?.logo_url ?? null;
  } catch {
    return new Response(null, { status: 502 });
  }
  if (!url) return new Response(null, { status: 404 });

  try {
    const remoto = await fetch(url, { signal: AbortSignal.timeout(5_000) });
    const tipo = (remoto.headers.get("content-type") ?? "").split(";")[0]!.trim().toLowerCase();
    if (!remoto.ok || !IMAGENES.has(tipo)) return new Response(null, { status: 404 });
    return new Response(remoto.body, {
      headers: { "content-type": tipo, "cache-control": "private, max-age=86400" },
    });
  } catch {
    return new Response(null, { status: 404 });
  }
}
