/**
 * Spec 052: cada negativa de la API sobre la invitación de propietario, en
 * palabras. El código lo decide la API; qué se le dice al operador, el panel.
 */
export const INVITATION_WORDS: Record<string, string> = {
  slug_taken:
    "Ese identificador ya está usado. Si acabas de intentarlo, puede que el partner ya exista: búscalo en Partners antes de repetir.",
  address_has_own_console: "Esa dirección ya tiene su propia consola: es de una persona de otro partner o de un cliente.",
  already_in_team: "Esa dirección ya es de una persona de este equipo. Su rol se cambia desde la consola del partner.",
  address_already_invited: "Esa dirección ya tiene otra invitación pendiente en este partner, emitida desde su consola.",
  invitation_pending: "Ya hay una invitación pendiente. Revócala antes de invitar a otra dirección.",
  has_active_owner: "Este partner ya tiene propietario activo: desde ahora su equipo lo gestiona él.",
  console_off: "La consola de este partner está apagada: enciéndela en Módulos para poder invitar o reenviar.",
  partner_suspended: "Este partner está suspendido: no se puede invitar ni reenviar.",
  partner_not_found: "Este partner ya no existe.",
  invitation_not_found: "Esa invitación ya no está. Recarga la pestaña.",
  invitation_accepted: "Esa persona ya aceptó la invitación: ya está dentro.",
  invitation_revoked: "Esa invitación ya estaba revocada: su enlace no sirve.",
  invitation_expired: "Esa invitación ya caducó: su enlace no sirve.",
};

/** La invitación ya no está viva: su enlace no sirve y no debe quedarse en pantalla. */
export const DEAD_INVITATION_CODES: ReadonlySet<string> = new Set([
  "invitation_accepted",
  "invitation_revoked",
  "invitation_expired",
  "invitation_not_found",
]);

/** Negativas que son de un campo del formulario. */
export const FIELD_OF_CODE: Readonly<Record<string, "slug" | "email">> = {
  slug_taken: "slug",
  address_has_own_console: "email",
  already_in_team: "email",
  address_already_invited: "email",
};

export const OWNER_EMAIL_REQUIRED = "Escribe el correo de quien va a ser su propietario.";
export const OWNER_EMAIL_BAD_SHAPE = "Eso no tiene forma de correo.";
export const UNKNOWN_OUTCOME =
  "No pudimos confirmar el resultado: la respuesta de la API se perdió. Puede que se haya hecho: compruébalo antes de repetir.";
export const RETRY_UNKNOWN =
  "No pudimos confirmar el reintento, y puede que el enlace que tenías ya no sirva. No lo pases: revisa la invitación en la pestaña Equipo del partner y reenvíala desde allí.";
export const PARTNER_MAY_EXIST =
  "No pudimos confirmar si se creó: la respuesta de la API se perdió. Búscalo en Partners antes de repetir; si está, reenvía la invitación desde su pestaña Equipo.";
/** Hasta 25 s si el proveedor no responde: un botón girando sin más parece colgado. */
export const SENDING_HINT = "Enviando el correo. Si el proveedor no responde, puede tardar hasta medio minuto.";
export const OPERATOR_DISABLED = "Tu cuenta de operador está deshabilitada.";
