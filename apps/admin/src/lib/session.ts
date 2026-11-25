/**
 * Sesión del panel — cookie opaca + una llamada a la API (ADR-034).
 *
 * La cookie sólo lleva un token que no significa nada fuera de la API: ni
 * el correo, ni el rol, ni una firma que el panel pudiera verificar por su
 * cuenta. Quien decide quién eres es siempre ``/admin/auth/session``.
 *
 * El middleware hace la comprobación barata (¿hay cookie?); este módulo
 * hace la de verdad, y por eso vive en Server Components y Server Actions.
 */

import "server-only";

import { revalidatePath } from "next/cache";
import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { clearImpersonateCookie } from "./impersonate";
import { endSession, login as apiLogin, resolveSession, type Operator } from "./operator-auth";
import { can, type Permission } from "./permissions";
import { safeRedirect } from "./safe-redirect";

/** Nombre propio, no el de Better Auth: una cookie vieja no debe parecer
 *  una sesión nueva. El prefijo ``__Host-`` en producción ata la cookie al
 *  host exacto y exige ``Secure`` + ``Path=/``, que es lo que quiere una
 *  cookie de sesión de un panel interno. */
const SECURE = process.env.NODE_ENV === "production";
export const SESSION_COOKIE = SECURE ? "__Host-nexus_operator" : "nexus_operator";

const MAX_AGE_SECONDS = 60 * 60 * 24 * 7; // 7 días, igual que el TTL de la API

export type { Operator };

export async function getOperator(): Promise<Operator | null> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  return resolveSession(token);
}

/**
 * Spec 078 + 079: la guarda del panel, una variante por superficie.
 *
 * El panel llama a la API con el token de servicio, así que la API no sabe qué
 * operador pide cada cosa: estas funciones son las que deciden si se obedece.
 * Cada Server Action, página, layout y ruta de `app/api` empieza por la suya
 * con el permiso que declara (`inventario.md` de la spec 079), y una prueba
 * estructural lo exige (`src/__tests__/server-actions-require-operator`).
 *
 * Sin sesión, al login. Una cuenta deshabilitada o con un rol que la matriz no
 * conoce no tiene ningún permiso: va a `/sin-acceso`, que mira lo mismo.
 */
async function activeOperator(): Promise<Operator> {
  const operator = await getOperator();
  if (!operator) redirect("/login");
  if (!can(operator, "read")) redirect("/sin-acceso");
  return operator;
}

/** El parámetro con el que la página dice «no se hizo nada» (spec 079, 2.2). */
export const DENIED_PARAM = "sin-permiso";

function logDenied(operator: Operator, permission: Permission, surface: "action" | "page" | "route"): void {
  // Una línea estructurada para los registros del panel. Nunca los argumentos
  // de la acción: pueden llevar datos de un cliente (spec 079, 2.3).
  console.warn(
    JSON.stringify({
      event: "operator.permission_denied",
      operator_id: operator.id,
      role: operator.role,
      permission,
      surface,
    }),
  );
}

/**
 * La página desde la que se lanzó la acción, solo si es de este mismo panel.
 * Las Server Actions se envían a la URL de su propia página, así que el
 * `Referer` es esa página; el panel no fija `Referrer-Policy` y el navegador
 * manda la ruta entera dentro del mismo origen. La ruta pasa por
 * `safeRedirect()`, el mismo filtro que la vuelta del login (spec 078, 4.1).
 */
async function samePageWithNotice(): Promise<string> {
  const h = await headers();
  const referer = h.get("referer");
  const host = h.get("x-forwarded-host") ?? h.get("host");
  let path = "/";
  if (referer && host) {
    try {
      const url = new URL(referer);
      if (url.host === host) path = safeRedirect(`${url.pathname}${url.search}`, "/");
    } catch {
      path = "/";
    }
  }
  const target = new URL(path, "https://panel.invalid");
  target.searchParams.set(DENIED_PARAM, "1");
  return `${target.pathname}${target.search}`;
}

/**
 * Para Server Actions. Sin el permiso, no llama a la API: deja rastro, invalida
 * el layout (el menú y los controles vuelven a pintarse con el rol vigente) y
 * vuelve a la misma página con el aviso (spec 079, 2.2).
 */
export async function requireOperator(permission: Permission): Promise<Operator> {
  const operator = await activeOperator();
  if (can(operator, permission)) return operator;
  logDenied(operator, permission, "action");
  const target = await samePageWithNotice();
  revalidatePath("/", "layout");
  redirect(target);
}

/**
 * Para páginas, layouts y `generateMetadata` de `app/(dashboard)`. Sin el
 * permiso, «no encontrada»: no se explica qué falta (constitución §V, spec 079,
 * 2.7).
 */
export async function requirePageOperator(permission: Permission): Promise<Operator> {
  const operator = await activeOperator();
  if (can(operator, permission)) return operator;
  logDenied(operator, permission, "page");
  notFound();
}

/**
 * Para rutas de `app/api`, que piden `fetch` y flujos de eventos: **nunca
 * redirige**. Devuelve el operador o la respuesta que la ruta tiene que
 * devolver tal cual, sin llamar a la API (spec 078, 2.3; spec 079, 2.5).
 */
export async function routeOperator(permission: Permission): Promise<Operator | Response> {
  const operator = await getOperator();
  if (!operator) return Response.json({ error: "unauthorized" }, { status: 401 });
  if (!can(operator, permission)) {
    if (can(operator, "read")) logDenied(operator, permission, "route");
    return Response.json({ error: "forbidden" }, { status: 403 });
  }
  return operator;
}

/**
 * Abre sesión y deja la cookie puesta. Devuelve el operador o el motivo
 * del fallo, sin traducirlo: quien pinta el mensaje es el formulario.
 *
 * Un operador con ``access !== "ok"`` **entra igual** —la cookie se pone—
 * y ``requireOperator()`` lo lleva a ``/sin-acceso``. Distinguirlo aquí sería
 * reintroducir por la puerta de atrás el oráculo que la API evita.
 */
export async function startSession(
  email: string,
  password: string,
): Promise<{ ok: true; operator: Operator } | { ok: false; reason: string; retryAfter?: number }> {
  const result = await apiLogin(email, password);
  if (!result.ok) return result;
  const jar = await cookies();
  jar.set(SESSION_COOKIE, result.token, {
    httpOnly: true,
    secure: SECURE,
    sameSite: "lax",
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
  return { ok: true, operator: result.operator };
}

/** Cierra la sesión en la API y borra la cookie. Idempotente. */
export async function closeSession(): Promise<void> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  jar.delete(SESSION_COOKIE);
  await clearImpersonateCookie();
  if (token) await endSession(token);
}
