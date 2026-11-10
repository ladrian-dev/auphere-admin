import { z } from "zod";

import { BackendError, callFor } from "@/lib/backend";
import { searchApi } from "@/lib/backend/search";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * Spec 047 (R47.2) — la paleta ⌘K del marco nuevo busca desde el navegador,
 * así que pasa por aquí: el marco no es una página y una acción de servidor
 * no se puede interceptar ni cancelar mientras se escribe.
 *
 * La forma de seguridad es la de siempre (D1 de `docs/companion/PLAN-CO-03.md`):
 * el principal se resuelve en el servidor, solo una persona de partner busca, y
 * cada llamada lleva un token de 60 s recién emitido. El navegador no tiene
 * credenciales. Qué acciones puede hacer la persona lo decide la API (§V).
 */
const query = z.object({ q: z.string().max(120).default("") });

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function GET(request: Request): Promise<Response> {
  const parsed = query.safeParse(Object.fromEntries(new URL(request.url).searchParams));
  if (!parsed.success) return json(422, { detail: "Invalid parameters" });
  const res = await resolvePrincipal();
  if (res.kind === "anonymous") return json(401, { detail: "Not signed in" });
  if (res.kind !== "ok" || res.principal.kind !== "partner") return json(403, { detail: "Not a partner member" });
  try {
    return json(200, await searchApi(callFor(res.principal)).search(parsed.data.q.trim()));
  } catch (err) {
    // El estado viaja; el cuerpo de la API y su URL no: la paleta solo dice
    // «La búsqueda falló» y el detalle queda en el registro del servidor.
    if (err instanceof BackendError) return json(err.status, { detail: "Search failed" });
    return json(502, { detail: "Search failed" });
  }
}
