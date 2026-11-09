import type { MessageKey } from "@/i18n/messages";
import type { AgentAgenda, NotReadyReason } from "@/lib/backend/agenda-types";
import { NOT_READY_REASONS } from "@/lib/backend/agenda-types";
import { clientHref } from "@/components/shell/routes-v2";

/**
 * Spec 057 — lo que la consola decide sobre la agenda de un agente sin pintar
 * nada: qué dice su fila, qué le falta a Reservas y dónde se completa, qué aviso
 * lleva la ficha del agente y adónde lleva una sección de la ficha. Puro: lo
 * prueban los tests sin montar la pantalla.
 */

const KNOWN: ReadonlySet<string> = new Set(NOT_READY_REASONS);

/** Lo que falta, una vez cada cosa y en el orden de la API. */
export function notReadyReasons(missing: readonly string[] | null | undefined): string[] {
  return [...new Set((missing ?? []).filter((m) => typeof m === "string" && m))];
}

/** El texto de un motivo; uno que la consola no conoce, «Falta algo por completar en Reservas». */
export function reasonKey(code: string): MessageKey {
  return (KNOWN.has(code) ? `agenda.notReady.reason.${code as NotReadyReason}` : "agenda.notReady.reason.other") as MessageKey;
}

/**
 * Dónde se completa cada motivo, si el partner puede ir (4.1). El horario y los
 * servicios son de la ficha (Negocio, compartida con Reservas); encender Reservas
 * es de Acceso. El equipo y las plazas de aforo los da de alta el cliente en su
 * Reservas, que el partner no abre: entonces no hay enlace y se dice dónde.
 */
export function reasonLink(refId: string, code: string): { href: string; label: MessageKey } | null {
  switch (code) {
    case "reservas_off":
      return { href: clientHref(refId, "access"), label: "agenda.notReady.toAccess" };
    case "hours_missing":
      return { href: `${clientHref(refId, "business")}#business-hours`, label: "builder.review.fix.hours" };
    case "no_services":
    case "no_bookable_service":
      return { href: `${clientHref(refId, "business")}#business-services`, label: "builder.review.fix.services" };
    default:
      return null;
  }
}

/** Lo completa el cliente en su Reservas: el equipo, las plazas o lo que la consola no conoce. */
export function completedByClient(code: string): boolean {
  return code !== "reservas_off" && code !== "hours_missing" && code !== "no_services" && code !== "no_bookable_service";
}

/**
 * El estado de la fila (2.1): activa en el borrador y en lo publicado, preparada
 * (en el borrador y no en lo publicado), quitándose (al revés) o sin activar.
 */
export type AgendaRowStatus = "on" | "prepared" | "leaving" | "off";
export function rowStatus(agenda: Pick<AgentAgenda, "draft" | "published">): AgendaRowStatus {
  if (agenda.draft.on) return agenda.published.on ? "on" : "prepared";
  return agenda.published.on ? "leaving" : "off";
}

/** «La agenda aún no está lista» (4.4): Reservas encendido y sin terminar. Apagado no es «sin terminar». */
export function notReady(agenda: Pick<AgentAgenda, "offered" | "module" | "ready"> | null | undefined): boolean {
  return Boolean(agenda?.offered && agenda.module.on && !agenda.ready);
}

/**
 * El aviso de la ficha del agente (4.4, 5.3): sin terminar, si el agente lleva o
 * va a llevar la agenda, y «Tiene la agenda preparada» si el borrador la lleva y
 * lo publicado no. Pueden salir los dos.
 */
export function headerNotices(agenda: AgentAgenda | null | undefined): { notReady: boolean; prepared: boolean } {
  if (!agenda?.offered) return { notReady: false, prepared: false };
  return {
    notReady: notReady(agenda) && (agenda.draft.on || agenda.published.on),
    prepared: agenda.state === "prepared",
  };
}

/** ¿Sigue escribiéndose la propuesta de texto? */
export function proposalRunning(agenda: Pick<AgentAgenda, "job"> | null | undefined): boolean {
  const status = agenda?.job?.status;
  return status === "queued" || status === "running";
}

/** ¿Falló el trabajo de la propuesta sin dejar ninguna abierta? (3.5) */
export function proposalFailed(agenda: Pick<AgentAgenda, "job" | "proposal"> | null | undefined): boolean {
  return agenda?.job?.status === "failed" && agenda.proposal?.status !== "open";
}

/**
 * Una sección de la ficha que dice que el equipo confirma las citas (3.7), con su
 * enlace a Negocio: `policies.cancellation` → Políticas; `faqs.*` → Preguntas
 * frecuentes; lo demás, a Negocio sin más.
 */
export function fichaLink(refId: string, section: string): { href: string; label: MessageKey | null } {
  const business = clientHref(refId, "business");
  const head = section.split(".")[0] ?? "";
  if (head === "policies") return { href: `${business}#business-policies`, label: "agenda.ficha.section.policies" };
  if (head === "faqs") return { href: `${business}#business-faqs`, label: "agenda.ficha.section.faqs" };
  return { href: business, label: null };
}
