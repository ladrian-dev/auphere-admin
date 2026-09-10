// El mapa se importa del módulo puro, no del de sesión: es la misma tabla y
// así esta ruta no arrastra `server-only` a quien solo quiere leer permisos.
import { PERMISSIONS } from "@/lib/permissions";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * Quién está dentro — para la cáscara de escritorio (spec 002, D6).
 *
 * La lee el **proceso principal** de la aplicación con la cookie de la
 * partición humana, al arrancar y en cada cambio de la cookie de sesión. La
 * página cargada no participa, y el ambiente del agente no tiene esa partición
 * ni ese proceso. Es lo que hace ciertas dos cosas sin abrir canal alguno:
 * «cerrar sesión detiene el puente» (11.1) y «la misma persona vuelve sin
 * código».
 *
 * Tres respuestas y **nada más**: 200 con `user_id`, `partner_slug`, el idioma
 * de la cuenta (para que la barra hable como la consola) y —desde la spec
 * 003— la lista de `permissions` resuelta, para que la pantalla de operar
 * sepa si puede usar teammates sin adivinar el rol; 401 sin sesión; 403
 * `no_membership` con sesión pero sin partner — para que la barra no ofrezca
 * emparejar a quien no puede (2.4). Ni correo, ni rol, ni nombre.
 */
function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function GET(): Promise<Response> {
  const res = await resolvePrincipal();
  if (res.kind === "anonymous") return json(401, { code: "anonymous" });
  if (res.kind !== "ok") return json(403, { code: "no_membership" });
  return json(200, {
    user_id: res.principal.userId,
    partner_slug: res.principal.partnerSlug,
    locale: res.principal.locale,
    permissions: Object.entries(PERMISSIONS)
      .filter(([, roles]) => (roles as readonly string[]).includes(res.principal.role))
      .map(([permission]) => permission),
  });
}
