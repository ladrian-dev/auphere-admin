"use server";

/**
 * Server actions del login (ADR-034).
 *
 * El formulario ya no habla con Better Auth desde el navegador: manda las
 * credenciales al servidor de Next, que las reenvía a ``/admin/auth/login``
 * con el token de servicio del panel y guarda la cookie. La contraseña no
 * pasa por ningún cliente JS más que el propio campo del formulario.
 */

import { closeSession, startSession } from "@/lib/session";

export type LoginState = { error: string | null };

export async function loginAction(
  _prev: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  if (!email || !password) {
    return { error: "Escribe tu email y tu contraseña." };
  }

  const result = await startSession(email, password);
  if (result.ok) return { error: null };

  // Un solo mensaje para credenciales malas, cuenta inexistente y cuenta
  // bloqueada: la API los hace indistinguibles a propósito y el panel no
  // debe deshacerlo con textos distintos.
  if (result.reason === "rate_limited") {
    return {
      error: `Demasiados intentos. Prueba otra vez en ${result.retryAfter ?? 60} segundos.`,
    };
  }
  if (result.reason === "unavailable") {
    return { error: "No se pudo contactar con el servidor. Inténtalo de nuevo." };
  }
  return { error: "Email o contraseña incorrectos." };
}

export async function logoutAction(): Promise<void> {
  await closeSession();
}
