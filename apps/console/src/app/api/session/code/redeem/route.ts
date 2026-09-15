import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";

import { BackendError, consoleService } from "@/lib/backend";
import { setSessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * El canje del código de la app de escritorio — spec 009, Requisito 4.
 *
 * **Esta ruta es pública, y es la única del par que lo es.** Quien llega
 * todavía no tiene sesión: es lo que viene a conseguir. Lo que sustituye a la
 * cookie vive en la API — diez minutos y un solo uso — y el salto de aquí a la
 * API sí va autenticado, con la credencial de servicio.
 *
 * **Por qué la cookie se pone AQUÍ y no en la cáscara.** El proceso principal
 * pide con el `fetch` de su partición, así que la cookie que devuelva esta
 * respuesta **se guarda sola** donde tiene que guardarse. La aplicación nunca
 * ve el token, y el Requisito 2.1 de la spec 002 —la app no tiene
 * autenticación propia— sigue siendo cierto sin excepciones.
 */
const redeem = z.object({ code: z.string().min(1).max(32) });

export async function POST(request: NextRequest): Promise<NextResponse> {
  const parsed = redeem.safeParse(await request.json().catch(() => null));
  // Un cuerpo que no tiene la forma se contesta **igual** que un código que no
  // vale: distinguirlos diría si el código llegó a mirarse.
  if (!parsed.success) {
    return NextResponse.json({ code: "session_code_invalid" }, { status: 422 });
  }
  try {
    const result = await consoleService.redeemSessionCode(parsed.data);
    await setSessionToken(result.session_token, result.expires_at);
    return NextResponse.json({ ok: true });
  } catch (err) {
    if (err instanceof BackendError) {
      // Mismo cuerpo para todo lo que la API rechaza: quien prueba códigos no
      // aprende por qué falló (R4.5, R5.3).
      return NextResponse.json({ code: "session_code_invalid" }, { status: 422 });
    }
    throw err;
  }
}
