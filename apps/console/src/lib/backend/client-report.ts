import type { Call } from "../backend";
import type { Money } from "./money-types";

/**
 * Carril del informe de un cliente (spec 083): `GET /console/clients/{ref}/report`,
 * `specs/083-informe-del-piloto/contracts/console-api.md`. Se esparce en `backendFor`.
 *
 * Pide `conversations:read` y `usage:read`. `from` y `to` son días del calendario
 * del cliente (`YYYY-MM-DD`), los dos incluidos; la API contesta 422 con un código
 * si el periodo va al revés, pasa de 92 días o acaba después de hoy. Sin palabras
 * de nadie: los motivos son códigos (`cause`) y el dinero va en cien milésimas.
 */

export type ReportCause =
  | "escalated"
  | "booking_unbacked"
  | "booking_brake"
  | "no_balance"
  | "agent_cap"
  | "paused_agent"
  | "paused_channel"
  | "paused_client"
  | "archived_client"
  | "channel_problem"
  | "agent_unpublished"
  | "no_model"
  | "provider_failure"
  | "turn_limit"
  | "reception_loop"
  | "agenda_not_ready"
  | "other";

export type ReportWho = { agent: number; person: number; customer: number; total: number };

export type ClientReport = {
  from: string;
  to: string;
  timezone: string;
  since: string;
  until: string;
  generated_at: string;
  /** El cliente cierra solas las conversaciones inactivas (spec 064). */
  autoclose: boolean;
  targets: { without_person_pct: number; first_response_pct: number; first_response_seconds: number };
  conversations: {
    total: number;
    without_person: number;
    with_person: number;
    /** `null` sin conversaciones. */
    without_person_pct: number | null;
    /** Un día por fecha del periodo. */
    series: { day: string; without_person: number; with_person: number }[];
    /** 24 filas: la hora local del primer mensaje del contacto (enmienda 2026-11-27, 13.1). */
    by_hour: { hour: number; without_person: number; with_person: number }[];
    /** 7 filas, ISO: 1 es lunes y 7, domingo. */
    by_weekday: { weekday: number; without_person: number; with_person: number }[];
  };
  first_response: {
    /** Conversaciones con algún envío del agente: el denominador del porcentaje. */
    answered: number;
    within_target: number;
    within_target_pct: number | null;
    median_seconds: number | null;
    p90_seconds: number | null;
    /** Conversaciones del periodo sin ningún envío del agente. */
    unanswered: number;
  };
  incidents: {
    total: number;
    resolved: number;
    open: number;
    by_cause: { cause: ReportCause; total: number; resolved: number }[];
    /** Las más recientes primero; como mucho 100. */
    items: { at: string; cause: ReportCause; resolved_at: string | null }[];
    truncated: boolean;
  };
  booking_brake: { stopped: number; corrected: number; handed_over: number };
  /** `null`: el cliente no tiene Reservas. */
  agenda: {
    created: ReportWho;
    moved: ReportWho;
    cancelled: ReportWho;
    /** Las reservas sin confirmar que se liberaron solas. */
    released: number;
    reminders: { kind: "reminder" | "ask_confirmation"; sent: number; failed: number; skipped: number }[];
  } | null;
  /** `null`: no se pudo leer (el resto del informe vale). */
  spend: {
    currency: Money["currency"];
    total: Money;
    conversations: Money;
    client_tests: Money;
    schedules: Money;
    meta: Money;
    approx: boolean;
    per_conversation: Money | null;
  } | null;
};

export function clientReportApi(call: Call) {
  const enc = encodeURIComponent;
  return {
    clientReport: (ref: string, from: string, to: string) =>
      call<ClientReport>(`/console/clients/${enc(ref)}/report?${new URLSearchParams({ from, to }).toString()}`),
  };
}
