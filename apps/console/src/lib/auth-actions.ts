"use server";

import { z } from "zod";

import { BackendError, consoleService } from "./backend";
import { clearSessionToken, getSessionToken, setSessionToken } from "./session";

/**
 * Sign in / sign out as Server Actions (ADR-032).
 *
 * The browser never talks to the API: it posts here, this server calls
 * `/console/auth/*` with a 60-second service token and writes the
 * `httpOnly` cookie. Nothing about the credential reaches client JS.
 *
 * The failure vocabulary is deliberately narrow — `invalid` covers a
 * wrong password, an unknown e-mail AND a locked account, exactly as the
 * API answers, so the console cannot leak which of the three it was.
 */

const credentials = z.object({
  email: z.string().email(),
  // No minimum here: enforcing the 12-character policy at sign-in would
  // turn a short password into a different answer than a wrong one.
  password: z.string().min(1).max(256),
});

export type SignInResult = { ok: true } | { ok: false; reason: "invalid" | "rate_limited" | "error" };

export async function signInAction(raw: unknown): Promise<SignInResult> {
  const parsed = credentials.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  try {
    const result = await consoleService.login(parsed.data);
    await setSessionToken(result.token, result.expires_at);
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 401) return { ok: false, reason: "invalid" };
      if (err.status === 429) return { ok: false, reason: "rate_limited" };
      return { ok: false, reason: "error" };
    }
    throw err;
  }
}

/** Idempotent: kills the session in the API and drops the cookie either way. */
export async function signOutAction(): Promise<void> {
  const token = await getSessionToken();
  if (token) {
    try {
      await consoleService.logout(token);
    } catch (err) {
      // A backend hiccup must not strand the user in a session they asked
      // to end: the cookie goes regardless, and the token expires on its own.
      if (!(err instanceof BackendError)) throw err;
    }
  }
  await clearSessionToken();
}

/**
 * El alta, como Server Actions (spec 006).
 *
 * **`signUpAction` devuelve siempre `ok` cuando la API responde 202**, exista
 * o no el correo. No es descuido: es el requisito. Si esta capa distinguiera
 * los dos casos —aunque fuera para enseñar un mensaje más amable— reabriría
 * desde el navegador el oráculo que la API cierra a propósito.
 *
 * `disabled` es la bandera apagada, y quien lo recibe **no pinta el
 * formulario**: la ausencia se diseña, no se explica con un aviso.
 */

const signUpInput = z.object({
  email: z.string().email(),
  locale: z.enum(["es", "en"]).default("es"),
});

export type SignUpResult =
  | { ok: true }
  | { ok: false; reason: "invalid" | "rate_limited" | "disabled" | "error" };

export async function signUpAction(raw: unknown): Promise<SignUpResult> {
  const parsed = signUpInput.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  try {
    await consoleService.startSignup(parsed.data);
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 429) return { ok: false, reason: "rate_limited" };
      if (err.status === 503) return { ok: false, reason: "disabled" };
      return { ok: false, reason: "error" };
    }
    throw err;
  }
}

const completeInput = z.object({
  token: z.string().min(16).max(128),
  company_name: z.string().min(1).max(255),
  password: z.string().min(12).max(256),
  display_name: z.string().max(255).optional(),
});

export type CompleteSignupResult =
  | { ok: true; partnerSlug: string }
  | { ok: false; reason: "not_found" | "already_member" | "invalid" | "disabled" | "error" };

export async function completeSignupAction(raw: unknown): Promise<CompleteSignupResult> {
  const parsed = completeInput.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  const { token, ...body } = parsed.data;
  try {
    const result = await consoleService.completeSignup(token, body);
    // La sesión se abre aquí, igual que en el login: la cookie `httpOnly` la
    // escribe este servidor y el token nunca pasa por JS del navegador.
    await setSessionToken(result.session_token, result.expires_at);
    return { ok: true, partnerSlug: result.partner_slug };
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 404) return { ok: false, reason: "not_found" };
      if (err.status === 409) return { ok: false, reason: "already_member" };
      if (err.status === 503) return { ok: false, reason: "disabled" };
      if (err.status === 422) return { ok: false, reason: "invalid" };
      return { ok: false, reason: "error" };
    }
    throw err;
  }
}


/**
 * Recuperar la contraseña — spec 011.
 *
 * **`requestPasswordResetAction` devuelve `ok` siempre que la API conteste**,
 * exista o no la cuenta, se haya mandado el correo o no, y esté o no la
 * dirección pasada de tope. No es descuido: es el requisito (R1.3). Si esta
 * capa distinguiera alguno de los cuatro casos —aunque fuera para enseñar un
 * mensaje más amable— reabriría desde el navegador el oráculo que la API cierra
 * a propósito.
 *
 * Es lo mismo que hace `signUpAction`, con una diferencia que importa: allí
 * `429` sí se distingue, porque el alta puede permitírselo. Aquí **no**, porque
 * el tope se gasta por dirección y un «demasiados intentos» contestado sólo a
 * las direcciones registradas es el oráculo por otra puerta. Por eso la API ni
 * siquiera devuelve 429 en esta ruta.
 */

const resetRequestInput = z.object({ email: z.string().email() });

export type RequestPasswordResetResult = { ok: true } | { ok: false; reason: "invalid" | "error" };

export async function requestPasswordResetAction(raw: unknown): Promise<RequestPasswordResetResult> {
  const parsed = resetRequestInput.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  try {
    await consoleService.startPasswordReset(parsed.data);
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) return { ok: false, reason: "error" };
    throw err;
  }
}

const resetFinishInput = z.object({
  token: z.string().min(16).max(128),
  password: z.string().min(12).max(256),
});

export type FinishPasswordResetResult =
  | { ok: true }
  | { ok: false; reason: "dead_link" | "invalid" | "error" };

/**
 * **No abre sesión, y es D-5.** El canje ha cerrado todas las de esta persona;
 * la pantalla la lleva a la entrada y entra ella con su contraseña nueva, que
 * es la prueba de que el circuito funciona.
 *
 * `dead_link` cubre los tres casos muertos —inexistente, caducado y ya usado—
 * porque la API los contesta con el mismo 404 y el mismo cuerpo.
 */
export async function finishPasswordResetAction(raw: unknown): Promise<FinishPasswordResetResult> {
  const parsed = resetFinishInput.safeParse(raw);
  if (!parsed.success) return { ok: false, reason: "invalid" };
  const { token, password } = parsed.data;
  try {
    await consoleService.finishPasswordReset(token, { password });
    return { ok: true };
  } catch (err) {
    if (err instanceof BackendError) {
      if (err.status === 404) return { ok: false, reason: "dead_link" };
      if (err.status === 422) return { ok: false, reason: "invalid" };
      return { ok: false, reason: "error" };
    }
    throw err;
  }
}


/**
 * «Continuar con Google» — spec 006, Requisito 5.
 *
 * Sólo pide a dónde ir. El intercambio del código ocurre en el callback, que
 * es una ruta del servidor porque **Google redirige el navegador allí**, no a
 * una server action.
 *
 * **Si Google no está configurado o no responde, esto devuelve `null` y quien
 * llama no pinta el botón** (Requisito 5.6): el alta y el login con contraseña
 * tienen que seguir funcionando sin depender de un tercero.
 */
export async function googleStartAction(
  intent: "login" | "signup",
  returnTo?: string,
): Promise<string | null> {
  try {
    const { authorization_url } = await consoleService.googleStart(intent, returnTo);
    return authorization_url;
  } catch (err) {
    if (err instanceof BackendError) return null;
    throw err;
  }
}
