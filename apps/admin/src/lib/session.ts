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

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { endSession, login as apiLogin, resolveSession, type Operator } from "./operator-auth";

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

/** Para páginas y acciones que exigen sesión. Redirige al login si no hay. */
export async function requireOperator(): Promise<Operator> {
  const operator = await getOperator();
  if (!operator) redirect("/login");
  return operator;
}

/**
 * Abre sesión y deja la cookie puesta. Devuelve el operador o el motivo
 * del fallo, sin traducirlo: quien pinta el mensaje es el formulario.
 *
 * Un operador con ``access !== "ok"`` **entra igual** —la cookie se pone—
 * y es el layout el que le enseña "sin acceso". Distinguirlo aquí sería
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
  if (token) await endSession(token);
}
