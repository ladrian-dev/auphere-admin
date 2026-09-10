import { tokenFor } from "@/lib/backend";
import { env } from "@/lib/env";
import { can, resolvePrincipal } from "@/lib/principal";

/**
 * Proxy SSE de la bandeja de una persona (spec 003, R5.3).
 *
 * Mismo patrón que el stream del Companion: el principal se resuelve en el
 * servidor, se acuña un token de 60 s y el cuerpo se reenvía sin tocarlo. Lo
 * que cambia es el techo: **este stream no tiene historia**, así que cortarlo
 * no pierde nada — quien escucha vuelve a pedir `GET /inbox` al reconectar, y
 * por eso `maxDuration` puede ser corto sin coste.
 */
export const dynamic = "force-dynamic";
export const maxDuration = 300;

function json(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function GET(request: Request): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") return json(401, "Not signed in");
  if (!can(res.principal.role, "teammates:use")) return json(403, "Missing permission teammates:use");

  const token = await tokenFor(res.principal);
  const upstream = await fetch(`${env().NEXUS_BACKEND_URL}/console/teammates/inbox/stream`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    cache: "no-store",
    signal: request.signal,
    // @ts-expect-error — undici option: keep the response streaming.
    duplex: "half",
  });
  if (!upstream.ok || !upstream.body) return json(502, "Inbox stream unavailable");
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-store",
      "x-accel-buffering": "no",
      connection: "keep-alive",
    },
  });
}
