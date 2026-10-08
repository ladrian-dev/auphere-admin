/**
 * Spec 030: what each closed-vocabulary refusal of the client-access API
 * means for the operator. The API sends `detail.code`; the sentence lives
 * here, never in the backend.
 */
export const ACCESS_ERRORS: Record<string, string> = {
  no_partner:
    "Este cliente no está en ningún partner. Vincúlalo desde la ficha del partner antes de darle acceso.",
  archived: "El cliente está archivado: no se le puede dar acceso.",
  no_modules: "Elige al menos un módulo para encender el acceso.",
  inbox_requires_whatsapp: "La Bandeja de entrada necesita un WhatsApp conectado.",
  unknown_module: "Ese módulo no existe.",
  account_is_partner_member:
    "Ese correo ya es de un partner. Una cuenta no puede ser a la vez de un partner y de un cliente.",
  account_is_other_client: "Ese correo ya tiene acceso a la consola de otro cliente.",
  already_member: "Esa persona ya tiene acceso.",
  access_disabled: "Enciende el acceso antes de invitar a nadie.",
  not_an_invitation: "Solo se pueden reenviar invitaciones.",
  unknown_member: "Esa persona ya no está en la lista. Recarga la página.",
};

export const MODULE_LABELS: Record<"panel" | "inbox" | "usage", { label: string; description: string }> = {
  panel: { label: "Panel", description: "Cómo va su agente, lo que gasta y lo que le necesita." },
  inbox: {
    label: "Bandeja de entrada",
    description: "Sus conversaciones de WhatsApp: leer, tomar el control y contestar.",
  },
  usage: { label: "Consumo", description: "Su saldo, su gasto por día y el detalle técnico. Solo lectura." },
};

export const INELIGIBLE: Record<"no_partner" | "archived", string> = {
  no_partner: ACCESS_ERRORS.no_partner!,
  archived: ACCESS_ERRORS.archived!,
};
