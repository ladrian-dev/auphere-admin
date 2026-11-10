import type { Call } from "../backend";

/**
 * Spec 043, requisito 15: the six WhatsApp templates of Reservas and how each one
 * stands, `GET /console/lite/reservas/templates`. The API reads the mirror that
 * Meta's webhook and the pass that creates them keep; it never calls Meta. A
 * rejection travels as a code (Meta's free text stays in the partner console).
 */
export const RESERVAS_TEMPLATE_NAMES = [
  "reserva_confirmada",
  "reserva_pide_confirmacion",
  "reserva_recordatorio",
  "reserva_cambiada",
  "reserva_cancelada",
  "reserva_hueco_libre",
] as const;
export type ReservasTemplateName = (typeof RESERVAS_TEMPLATE_NAMES)[number];

export type ReservasTemplateState = "approved" | "in_review" | "rejected" | "paused" | "not_created";
export type ReservasTemplateRejection = "invalid_format" | "incorrect_category" | "promotional" | "abusive_content" | "other";
/** No WhatsApp number, about to be asked for, or deleted in Meta (never asked for again on its own). */
export type ReservasTemplateNotCreated = "no_whatsapp" | "on_its_way" | "deleted";

export type ReservasTemplate = {
  name: string;
  state: ReservasTemplateState;
  rejection: ReservasTemplateRejection | null;
  why_not_created: ReservasTemplateNotCreated | null;
  /** ISO instant of the last thing Meta said about it. */
  since: string | null;
};

export type ReservasTemplates = {
  /** The client has a Meta WhatsApp number connected. */
  whatsapp: boolean;
  approved: number;
  items: ReservasTemplate[];
};

export function reservasTemplatesApi(call: Call) {
  return {
    reservasTemplates: () => call<ReservasTemplates>("/console/lite/reservas/templates"),
  };
}
