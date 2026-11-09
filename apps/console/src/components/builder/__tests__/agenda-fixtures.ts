import type { ConnectorTools } from "@/lib/backend/agent-connectors-types";
import type { AgentAgenda } from "@/lib/backend/agenda-types";

/** Spec 057 — los datos de prueba de la agenda de un agente (`contracts/console-api.md` §3 y §5). */

export const AGENDA: AgentAgenda = {
  offered: true,
  module: { on: true, mode: "services", capacity_kind: null },
  ready: true,
  missing: [],
  draft: { on: false, tools_on: 0 },
  published: { on: false },
  state: "none",
  structured: true,
  proposal: null,
  job: null,
  suggested: { mode: "services", capacity_kind: null },
  can_write: true,
  max_tools: 60,
};
export const ON: AgentAgenda = { ...AGENDA, draft: { on: true, tools_on: 9 }, published: { on: true }, state: "on" };
export const AGENDA_TOOLS: ConnectorTools = {
  slug: "reservas",
  name: "Agenda (Reservas)",
  permission: null,
  tools: [
    {
      name: "reservas.find_slots",
      title: "Buscar huecos libres",
      description: "Mira la agenda.",
      read_only: true,
      enabled: true,
      enabled_in_active: true,
      locked: false,
      locked_by: null,
      needs_write_permission: false,
      suggested: true,
    },
    {
      name: "reservas.join_waitlist",
      title: "Apuntar en la lista de espera",
      description: "Apunta a quien escribe.",
      read_only: false,
      enabled: true,
      enabled_in_active: true,
      locked: false,
      locked_by: null,
      needs_write_permission: false,
      suggested: false,
    },
  ],
};
