import { NextResponse, type NextRequest } from "next/server";

import { BackendError, consoleService } from "@/lib/backend";
import { setSessionToken } from "@/lib/session";

/**
 * La vuelta de Google — spec 006, Requisito 5.
 *
 * **Es una ruta y no una server action porque Google redirige el navegador
 * aquí** con `?code=&state=`. Lo que llega en esa URL no se cree: se manda tal
 * cual a la API, que verifica el `state`, consume el PKCE y comprueba el
 * `id_token`. Este fichero no decide nada sobre la identidad.
 *
 * Los dos desenlaces terminan en un redirect, nunca en un JSON: quien llega
 * aquí es una persona con un navegador, no un programa.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const params = request.nextUrl.searchParams;
  const code = params.get("code");
  const state = params.get("state");

  // Google manda `error=access_denied` cuando la persona cancela. No es un
  // fallo: es una decisión, y se trata como tal — de vuelta al login, sin
  // ruido.
  if (params.get("error") || !code || !state) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  try {
    const result = await consoleService.googleCallback({ code, state });
    if (result.outcome === "session" && result.session_token) {
      await setSessionToken(result.session_token, result.expires_at ?? undefined);
      // **Spec 009, fallo 1** — volver a donde ibas.
      //
      // `return_to` sale del `state` **firmado** que la API verificó, no de la
      // URL: los parámetros de esta ruta los pone Google, y lo que no llega
      // firmado por nosotros no se puede creer. La API además sólo lo acepta si
      // es una ruta del mismo origen, así que esto no es un redirector abierto.
      const back = result.return_to;
      return NextResponse.redirect(new URL(back && back.startsWith("/") ? back : "/", request.url));
    }
    if (result.outcome === "signup_pending" && result.signup_token) {
      // Identidad buena, falta nombrar la empresa: sigue por el MISMO camino
      // que el alta con contraseña, que es donde vive esa pantalla.
      return NextResponse.redirect(new URL(`/signup/${result.signup_token}`, request.url));
    }
    return NextResponse.redirect(new URL("/login", request.url));
  } catch (err) {
    if (err instanceof BackendError) {
      // 403 es `email_not_verified`: Google afirma el correo pero no lo
      // respalda. Se distingue en la URL para poder explicarlo, porque aquí
      // la persona sí necesita saber por qué no entró — es su cuenta.
      const reason = err.status === 403 ? "email_unverified" : "google";
      return NextResponse.redirect(new URL(`/login?error=${reason}`, request.url));
    }
    throw err;
  }
}
