import type { WhatsAppOtpTemplateInput } from "@/lib/backend";

/** Meta's limit for the copy-code button. */
export const OTP_BUTTON_MAX = 25;
export const OTP_DEFAULT_BUTTON = "Copiar código";

export type OtpDraft = { buttonText: string; minutes: string; security: boolean };

/**
 * Spec 077 (3.1): Meta's fixed text of an authentication template, as the
 * customer reads it. It follows the fields: no security sentence when it is
 * off, no expiry line without minutes.
 */
export function otpPreview(draft: OtpDraft, code = "123456"): { body: string; footer: string | null; button: string } {
  const minutes = parseMinutes(draft.minutes);
  return {
    body: `${code} es tu código de verificación.${draft.security ? " Por tu seguridad, no lo compartas." : ""}`,
    footer: typeof minutes === "number" ? `Este código caduca en ${minutes} ${minutes === 1 ? "minuto" : "minutos"}.` : null,
    button: draft.buttonText.trim() || OTP_DEFAULT_BUTTON,
  };
}

/**
 * Whether the preview can show Meta's fixed text: it is written here in
 * Spanish, so it only stands for a template in Spanish (`es`, `es_CL`…).
 * For any other language Meta writes it in that language.
 */
export function isSpanishTemplate(language: string): boolean {
  return language.trim().toLowerCase().startsWith("es");
}

/** Empty: no expiry. A whole number 1–90: the minutes. Anything else: invalid. */
function parseMinutes(text: string): number | null | "invalid" {
  const t = text.trim();
  if (!t) return null;
  if (!/^\d+$/.test(t)) return "invalid";
  const n = Number(t);
  return n >= 1 && n <= 90 ? n : "invalid";
}

/** What is wrong with the draft, in words; empty when it can be sent. */
export function otpIssues(draft: OtpDraft): { button?: string; minutes?: string } {
  const issues: { button?: string; minutes?: string } = {};
  const button = draft.buttonText.trim();
  if (!button) issues.button = "Escribe el texto del botón.";
  else if (button.length > OTP_BUTTON_MAX) issues.button = `Como mucho ${OTP_BUTTON_MAX} caracteres.`;
  if (parseMinutes(draft.minutes) === "invalid") issues.minutes = "Un número entero de 1 a 90, o vacío para no decir caducidad.";
  return issues;
}

/** The `otp` the API builds Meta's format from (only with AUTHENTICATION). */
export function otpPayload(draft: OtpDraft): WhatsAppOtpTemplateInput {
  const minutes = parseMinutes(draft.minutes);
  return {
    button_text: draft.buttonText.trim(),
    ...(typeof minutes === "number" ? { code_expiration_minutes: minutes } : {}),
    add_security_recommendation: draft.security,
  };
}
