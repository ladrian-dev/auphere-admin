import { NextResponse } from "next/server";

import { BackendError, backendFor } from "@/lib/backend";
import { resolvePrincipal } from "@/lib/principal";

/**
 * Donde una máquina queda registrada — spec 012, Requisito 3.
 *
 * Sustituye al canje del código de ocho símbolos. La diferencia no es el
 * resultado —la misma credencial, para la misma máquina, de la misma persona—
 * sino quién demuestra tener derecho a pedirla: antes un código tecleado, ahora
 * la sesión que la aplicación ya tenía. Para poder teclear aquel código, la
 * aplicación **ya** tenía esta sesión confirmada; el segundo acto no probaba
 * nada, y además es el patrón que explotó Storm-2372 contra el device code flow.
 *
 * **Por qué pasa por aquí y no por la API directamente.** El mismo motivo que
 * `redeem`, y está aprendido a base de un fallo desplegado: la ruta de la API
 * exige la credencial de servicio del BFF y la cáscara no tiene ninguna ni
 * puede tenerla. Llamar directo devuelve `401 Missing bearer token`.
 *
 * **Y por qué ésta SÍ devuelve cuerpo**, al revés que `redeem`. Aquélla entrega
 * una **cookie**, que viaja sola a la partición; ésta entrega una **credencial
 * de máquina** que la aplicación guarda cifrada en el llavero del sistema. Es la
 * única ruta del BFF que devuelve un secreto, y de ahí sale la regla: se entrega
 * una vez y no se puede volver a leer.
 *
 * **Por qué no se reutiliza `redeem`**: ata otra cosa. Aquélla ata una *persona*
 * a la aplicación; ésta ata una *máquina* a la cuenta. ADR-039 avisó justo de
 * esta confusión — «se parecen y atan cosas distintas».
 */
export async function POST(request: Request): Promise<NextResponse> {
  const resolution = await resolvePrincipal();
  // Unión discriminada: solo `ok` trae principal. Los demás casos —anónimo, sin
  // membresía, suspendido, consola apagada— no tienen a quién registrar.
  if (resolution.kind !== "ok") {
    // Sin sesión no hay nada que mirar. El mismo cuerpo que da la API cuando la
    // sesión es vieja: las dos llevan al mismo sitio, que es entrar de nuevo.
    return NextResponse.json({ code: "session_not_recently_confirmed" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ code: "bad_request" }, { status: 400 });
  }

  const {
    hostname,
    platform,
    install_id: installId,
    app_version: appVersion,
  } = (body ?? {}) as Record<string, unknown>;

  // Los mismos mínimos que declara la API, comprobados antes de gastar un token
  // en una llamada que ya se sabe que no vale.
  const ok =
    typeof hostname === "string" &&
    hostname.length > 0 &&
    hostname.length <= 255 &&
    (platform === "macos" || platform === "windows") &&
    typeof installId === "string" &&
    installId.length >= 8 &&
    installId.length <= 128 &&
    (appVersion === undefined || (typeof appVersion === "string" && appVersion.length <= 32));
  if (!ok) return NextResponse.json({ code: "bad_request" }, { status: 400 });

  try {
    const registered = await backendFor(resolution.principal).registerMachine({
      hostname,
      platform,
      install_id: installId,
      ...(typeof appVersion === "string" ? { app_version: appVersion } : {}),
    });
    return NextResponse.json(registered, { status: 201 });
  } catch (err) {
    if (err instanceof BackendError) {
      // El tope dice que es el tope: es información de quien pregunta, y saberlo
      // es lo que le dice qué hacer. Lo demás va con el cuerpo de la sesión.
      if (err.status === 409) {
        return NextResponse.json({ code: "machine_cap_reached" }, { status: 409 });
      }
      return NextResponse.json({ code: "session_not_recently_confirmed" }, { status: 401 });
    }
    throw err;
  }
}
