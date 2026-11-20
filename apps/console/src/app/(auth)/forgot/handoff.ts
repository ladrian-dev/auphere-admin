/**
 * El correo que pasa de Entrar a Recuperar la cuenta — spec 066, R4.3.
 *
 * Va por `sessionStorage` y no por la URL: una URL acaba en el historial, en los
 * registros del servidor y en la cabecera `Referer`. Se lee una vez y se borra.
 * Si el almacenamiento no está disponible (modo privado estricto), no pasa nada:
 * la persona escribe el correo.
 */
export const FORGOT_EMAIL_KEY = "nexus-console.forgot-email";

export function rememberEmailForForgot(email: string | undefined): void {
  const v = (email ?? "").trim();
  try {
    if (v) sessionStorage.setItem(FORGOT_EMAIL_KEY, v);
    else sessionStorage.removeItem(FORGOT_EMAIL_KEY);
  } catch {
    /* sin almacenamiento: se escribe a mano */
  }
}

export function takeEmailForForgot(): string {
  try {
    const v = sessionStorage.getItem(FORGOT_EMAIL_KEY) ?? "";
    sessionStorage.removeItem(FORGOT_EMAIL_KEY);
    return v;
  } catch {
    return "";
  }
}
