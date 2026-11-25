import { BackendError, backendFor } from "@/lib/backend";
import { can, resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * `GET /api/notifications/count` — el número de la campana (CP-29, spec 071):
 * los avisos sin leer más lo que te necesita ahora («Ahora», la misma lista del
 * Panel). Si «Ahora» no se puede leer, cuenta solo los avisos.
 *
 * La campana lo pregunta al montar, al cambiar de página y cada 60 s. Antes eran
 * dos acciones de servidor, y una acción de servidor pasa por la cola del router:
 * la que salía justo al pulsar un enlace volvía, al terminar, a la página de la
 * que se había salido (spec 074, el e2e de «Repartir tu saldo en bolsas»). Una
 * lectura en segundo plano no navega, así que va por aquí, como la búsqueda.
 *
 * La forma de seguridad es la de siempre: el principal se resuelve en el
 * servidor y cada llamada lleva un token recién emitido. El navegador no tiene
 * credenciales.
 */
function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function GET(): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind === "anonymous") return json(401, { detail: "Not signed in" });
  if (res.kind !== "ok" || !can(res.principal.role, "partner:read")) return json(403, { detail: "Forbidden" });
  const api = backendFor(res.principal);
  try {
    const [notifications, now] = await Promise.all([api.unreadNotifications(), api.attention().catch(() => null)]);
    return json(200, { unread: notifications.unread + (now?.items.length ?? 0) });
  } catch (err) {
    // El estado viaja; el cuerpo de la API no: la campana se queda con su último número.
    if (err instanceof BackendError) return json(err.status, { detail: "Count failed" });
    return json(502, { detail: "Count failed" });
  }
}
