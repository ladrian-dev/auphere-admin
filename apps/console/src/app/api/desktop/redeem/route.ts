import { NextResponse } from "next/server";

import { BackendError, consoleService } from "@/lib/backend";
import { setSessionToken } from "@/lib/session";

/**
 * Donde termina el inicio de sesión de la aplicación — spec 009, Requisito 4.
 *
 * **Por qué el canje pasa por aquí y no por la API directamente.** La ruta de
 * la API exige la credencial de servicio del BFF (`require_console_service`),
 * y la cáscara no tiene ninguna ni puede tenerla: la consola nunca guarda una
 * credencial de backend, y CI lo comprueba. La cáscara llamaba a la API por su
 * cuenta y recibía `401 Missing bearer token` — el inicio de sesión no
 * terminaba nunca y no se veía, porque en el navegador todo salía bien.
 *
 * **Y por qué contesta 204 y no el token.** La sesión de la aplicación es la
 * cookie de ESTE origen: la cáscara canjea con el `fetch` de su partición
 * humana, la cookie cae en esa partición, y su `SessionGate` la ve. Devolver el
 * token en el cuerpo obligaría a la cáscara a guardarlo, que es justo lo que el
 * diseño no quiere que haga.
 *
 * El rechazo es **uno solo**: caducado, usado, inexistente o con otro verifier
 * se contestan igual, como en la API. Distinguirlos aquí desharía su trabajo.
 */
export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ code: "bad_request" }, { status: 400 });
  }

  const { code, code_verifier: verifier } = (body ?? {}) as Record<string, unknown>;
  // Los mismos mínimos que declara la API, comprobados antes de gastar un
  // token de servicio en una llamada que ya se sabe que no vale.
  const ok =
    typeof code === "string" &&
    code.length > 0 &&
    code.length <= 32 &&
    typeof verifier === "string" &&
    verifier.length >= 32 &&
    verifier.length <= 256;
  if (!ok) return NextResponse.json({ code: "bad_request" }, { status: 400 });

  try {
    const result = await consoleService.redeemSessionCode({ code, code_verifier: verifier });
    await setSessionToken(result.session_token, result.expires_at);
    return new NextResponse(null, { status: 204 });
  } catch (err) {
    if (err instanceof BackendError) {
      return NextResponse.json({ code: "session_code_invalid" }, { status: 401 });
    }
    throw err;
  }
}
