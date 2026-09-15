import { redirect } from "next/navigation";

import { backendFor } from "@/lib/backend";
import { isLoopbackRedirect } from "@/lib/desktop-redirect";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

/**
 * Donde empieza y termina el inicio de sesión de la aplicación de escritorio
 * — spec 009 (2ª enmienda), RFC 8252.
 *
 * La cáscara abre el navegador aquí con `redirect_uri`, `state` y
 * `code_challenge`. Dos desenlaces:
 *
 * * **Sin sesión** → a `/login`, con `next` puesto para volver. Sin eso, quien
 *   entra con Google acaba en la portada de la consola y la aplicación no se
 *   entera nunca — que es exactamente el fallo 1 que esta spec vino a cerrar.
 * * **Con sesión** → se emite el código y se devuelve por redirección.
 *
 * **Nada se emite antes de validar el `redirect_uri`**, y el orden importa: si
 * se emitiera primero, un `redirect_uri` ajeno dejaría un código vivo por ahí
 * aunque no se llegara a redirigir.
 *
 * Esta pantalla **no se pinta nunca**: los dos caminos redirigen. Es una ruta
 * con forma de página porque necesita la sesión del servidor.
 */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const one = (k: string): string => (Array.isArray(params[k]) ? params[k][0] : params[k]) ?? "";
  const redirectUri = one("redirect_uri");
  const state = one("state");
  const challenge = one("code_challenge");

  // Lista blanca de host, parseada. Ver `lib/desktop-redirect.ts`: sin esto
  // la ruta es un redirector abierto.
  if (!isLoopbackRedirect(redirectUri) || !state || !challenge) {
    redirect("/no-access");
  }

  const res = await resolvePrincipal();
  if (res.kind !== "ok") {
    // Se conserva la petición entera para volver a ella tras entrar.
    const self = `/desktop-auth?redirect_uri=${encodeURIComponent(redirectUri)}&state=${encodeURIComponent(state)}&code_challenge=${encodeURIComponent(challenge)}`;
    redirect(`/login?from=${encodeURIComponent(self)}`);
  }

  const { code } = await backendFor(res.principal).issueSessionCode({ code_challenge: challenge });
  const back = new URL(redirectUri);
  back.searchParams.set("code", code);
  back.searchParams.set("state", state);
  redirect(back.toString());
}
