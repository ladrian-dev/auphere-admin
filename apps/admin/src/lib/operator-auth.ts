/**
 * Cliente de ``/admin/auth/*`` — la identidad del panel vive en la API.
 *
 * ADR-034. Antes esto era Better Auth + Drizzle contra Postgres, y por eso
 * ``admin.auphere.com`` se cayó el 2026-08-19 en cuanto la base de Railway
 * se apagó: la Aurora que la sustituye es privada y una función de Vercel
 * no la alcanza. Ahora el panel **no tiene base de datos**. Guarda una
 * cookie con un token opaco que sólo significa algo en la API.
 *
 * Vive aparte de ``lib/backend.ts`` a propósito. Aquel convierte cualquier
 * respuesta no-2xx en un ``BackendError``, que es lo correcto para los
 * endpoints de datos y lo contrario de lo que quiere un login: aquí un 401
 * es una **respuesta esperada** —contraseña mala— y un 429 es información
 * que hay que enseñar al usuario, no un fallo que propagar.
 *
 * Server-side only: lleva el bearer del panel y nunca puede llegar al
 * navegador.
 */

import "server-only";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8000";
const ADMIN_TOKEN = process.env.NEXUS_ADMIN_TOKEN ?? "dev-admin-token-change-me";

/** Roles que la API devuelve. Sólo gatean el QA Playground. */
export const QA_ROLES = ["admin", "qa_operator"] as const;
export type Role = (typeof QA_ROLES)[number] | "viewer";

export type Operator = {
  id: string;
  email: string;
  display_name: string | null;
  locale: string;
  /** ``disabled`` = la cuenta existe pero ya no puede operar. */
  access: "ok" | "disabled";
  role: Role;
};

export type LoginResult =
  | { ok: true; token: string; expiresAt: string; operator: Operator }
  | { ok: false; reason: "invalid" | "rate_limited" | "unavailable"; retryAfter?: number };

async function post<T>(path: string, body: unknown): Promise<{ status: number; data: T | null; headers: Headers }> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const text = await res.text();
  let data: T | null = null;
  if (text) {
    try {
      data = JSON.parse(text) as T;
    } catch {
      data = null;
    }
  }
  return { status: res.status, data, headers: res.headers };
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const { status, data, headers } = await post<{
    token: string;
    expires_at: string;
    operator: Operator;
  }>("/admin/auth/login", { email, password });

  if (status === 200 && data) {
    return { ok: true, token: data.token, expiresAt: data.expires_at, operator: data.operator };
  }
  if (status === 429) {
    const retry = Number(headers.get("Retry-After") ?? "60");
    return { ok: false, reason: "rate_limited", retryAfter: Number.isFinite(retry) ? retry : 60 };
  }
  // 401 es lo normal: contraseña mala, correo inexistente o cuenta
  // bloqueada — la API los hace indistinguibles a propósito y el panel no
  // debe deshacer ese trabajo inventando mensajes distintos.
  if (status === 401) return { ok: false, reason: "invalid" };
  return { ok: false, reason: "unavailable" };
}

/** ``null`` = no hay sesión. Es una respuesta normal, no un error. */
export async function resolveSession(token: string): Promise<Operator | null> {
  if (!token) return null;
  const { status, data } = await post<{ operator: Operator | null }>("/admin/auth/session", {
    token,
  });
  if (status !== 200 || !data) return null;
  return data.operator;
}

/** Idempotente, y a prueba de que la API no conteste: cerrar sesión en el
 *  navegador (borrar la cookie) no puede depender de que el backend
 *  responda. */
export async function endSession(token: string): Promise<void> {
  if (!token) return;
  try {
    await post("/admin/auth/logout", { token });
  } catch {
    // Da igual: la cookie se borra igualmente y el token caduca solo.
  }
}
