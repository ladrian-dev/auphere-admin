import { redirect } from "next/navigation";

import { backendFor } from "@/lib/backend";
import { resolvePrincipal } from "@/lib/principal";

import { DesktopCode } from "./desktop-code";

export const dynamic = "force-dynamic";

/**
 * Emite el código al entrar — spec 009, R3.1.
 *
 * **Se emite al pintar la página y no en un botón**, porque quien llega ya ha
 * hecho lo único que había que hacer: entrar con Google. Pedirle un clic más
 * sería cobrarle por el camino de vuelta.
 *
 * Y se emite **con su sesión**: la API lo crea para quien lo pide y para nadie
 * más. Sin sesión aquí no hay nada que llevarse, así que se manda a `/login`.
 *
 * Si la emisión falla, se pinta sin código. **No se reintenta en bucle ni se
 * finge uno**: la pantalla lo dice y la persona vuelve a intentarlo desde la
 * aplicación (§V).
 */
export default async function Page() {
  const res = await resolvePrincipal();
  if (res.kind !== "ok") redirect("/login?from=/desktop-code");

  let code: string | null = null;
  try {
    code = (await backendFor(res.principal).issueSessionCode()).code;
  } catch {
    code = null;
  }
  return <DesktopCode code={code} />;
}
