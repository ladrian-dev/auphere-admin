/**
 * Spec 059 (historia 6; 6.1–6.5): the words and the rules of Números de
 * Auphere. Pure, so they are tested on their own.
 */
import type { AuphereOwnerChannelOut } from "@/lib/backend";

/** The same rule as the API (`schemas/auphere_channels.py`): `+`, the country prefix, up to 15 digits. */
const PHONE = /^\+[1-9]\d{1,14}$/;
const ISO2 = /^[A-Za-z]{2}$/;

/** The API keeps up to 500 characters of reason (`auphere_channels.REASON_MAX`). */
export const REASON_MAX = 500;

export function phoneError(raw: string): string | null {
  const text = raw.trim();
  if (!text) return "Hace falta el número.";
  if (!PHONE.test(text)) return "Escribe el número con el prefijo del país y sin espacios, por ejemplo +34600111222.";
  return null;
}

export function nameError(raw: string): string | null {
  const text = raw.trim();
  if (!text) return "Hace falta un nombre.";
  if (text.length > 120) return "Como mucho 120 caracteres.";
  return null;
}

export function countryError(raw: string): string | null {
  const text = raw.trim();
  if (!text) return null;
  return ISO2.test(text) ? null : "El código de dos letras del país, por ejemplo ES o CL.";
}

export function reasonError(raw: string): string | null {
  const text = raw.trim();
  if (!text) return "Hace falta el motivo.";
  if (text.length > REASON_MAX) return `Como mucho ${REASON_MAX} caracteres.`;
  return null;
}

/** A number sends only with its token and its Meta number id (`ResolvedAuphereChannel.can_send`). */
export function canSend(n: AuphereOwnerChannelOut): boolean {
  return n.has_access_token && Boolean(n.provider_phone_id);
}

/**
 * The API's refusals, in the panel's words. The API answers these with a
 * sentence in English (`detail`), not a code, so the status and its sentence
 * decide.
 */
export function numberFailure(status: number | null, detail: unknown): string {
  const said = typeof detail === "string" ? detail : "";
  if (status === 409 && /already has a default/.test(said)) {
    return "Ya hay un número principal. Quítale esa marca antes de dársela a otro.";
  }
  if (status === 409) return "Ese número ya está registrado.";
  if (status === 404) return "Ese número ya no existe. Recarga la página.";
  if (status === 400) return "La API no reconoce a la persona de tu sesión. Vuelve a entrar en el panel.";
  if (status === 401 || status === 403) return "El panel no tiene permiso para cambiar los números de Auphere.";
  if (status === 422) return "Revisa los campos: la API no los acepta.";
  return status ? `La API respondió ${status}.` : "La API no respondió. Vuelve a intentarlo en un momento.";
}
