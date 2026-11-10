/**
 * Tipos puros de la agenda de un agente (spec 057, `contracts/console-api.md`
 * §3–§5). Sin imports con efectos: valen para componentes de cliente y para los
 * tests. El cliente de la API es `./agenda.ts`.
 */
import type { ReservasChoice } from "./builder-types";
import type { CapacityKind, ReservasMode } from "./client-access";

export type { ReservasChoice } from "./builder-types";

/** `none`: el borrador no la lleva. `prepared`: el borrador sí y la versión activa no. `on`: la activa la lleva. */
export type AgendaState = "none" | "prepared" | "on";

/** Los motivos de `passing.NOT_READY_REASONS`: lo que le falta al cliente para tomar una cita. */
export const NOT_READY_REASONS = ["reservas_off", "hours_missing", "no_staff", "no_services", "no_bookable_service", "no_capacity"] as const;
export type NotReadyReason = (typeof NOT_READY_REASONS)[number];

export type AgendaTextStatus = "open" | "stale" | "applied" | "rejected" | "expired";

/** `GET /console/clients/{ref}/agents/{id}/agenda` (§3) y la respuesta del `PUT` (§4). */
export type AgentAgenda = {
  /** Reservas se ofrece a este cliente. Falso: no hay fila ni interruptor (§V). */
  offered: boolean;
  module: { on: boolean; mode: ReservasMode | null; capacity_kind: CapacityKind | null };
  ready: boolean;
  /** Códigos de `NOT_READY_REASONS`; vacío si está lista. */
  missing: string[];
  draft: { on: boolean; tools_on: number };
  published: { on: boolean };
  state: AgendaState;
  /** Falso: agente de instrucciones libres, sin propuesta de texto (2.7). */
  structured: boolean;
  proposal: { id: string; status: AgendaTextStatus } | null;
  /** El trabajo que escribe la propuesta, si hay uno. */
  job: { id: string; status: string } | null;
  suggested: { mode: ReservasMode | null; capacity_kind: CapacityKind | null };
  can_write: boolean;
  max_tools: number;
  /** Solo en la respuesta del `PUT`: por qué no hay propuesta. */
  proposal_reason?: "build_budget_exhausted" | "not_structured" | null;
};

/** El cuerpo del `PUT` (`extra="forbid"`): nunca `tenant_id` ni `partner_id`. */
export type AgendaBody = { enabled: boolean; reservas?: ReservasChoice };
