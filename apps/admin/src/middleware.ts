/**
 * Edge middleware — deja pasar ``/login`` y manda al login todo lo demás
 * sin cookie de sesión.
 *
 * Comprobación barata, sin llamar a la API: sólo mira que la cookie EXISTA.
 * La verificación de verdad la hacen los Server Components y las Server
 * Actions con ``getOperator()`` / ``requireOperator()``, que preguntan a
 * ``/admin/auth/session``. Aquí sólo se trata de no montar un layout entero
 * para alguien que ni siquiera trae credencial.
 */

import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login"];

/** Los dos nombres posibles según entorno (ver ``lib/session.ts``). El
 *  middleware corre en el edge y no puede importar ``server-only``, así que
 *  la lista se repite aquí a propósito. */
const SESSION_COOKIES = ["__Host-nexus_operator", "nexus_operator"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }
  const hasSession = SESSION_COOKIES.some((name) => request.cookies.has(name));
  if (!hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("from", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match every request except:
     * - ``_next/static`` / ``_next/image`` / favicon (Next internals)
     * - any file with an extension (assets)
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)",
  ],
};
