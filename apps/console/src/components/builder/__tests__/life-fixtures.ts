import type { ClientAgent } from "@/lib/backend";
import type { AgentHeader } from "@/lib/backend/agent-life-types";

/** Spec 047 (T124) — los agentes de un cliente y la cabecera de uno. */

export const REF = "barberia-cultor";
export const RECEPCION = "11111111-1111-4111-8111-111111111111";
export const COBROS = "22222222-2222-4222-8222-222222222222";
export const VENTAS = "33333333-3333-4333-8333-333333333333";
export const CH1 = "44444444-4444-4444-8444-444444444441";
export const CH2 = "44444444-4444-4444-8444-444444444442";

export const ok = <T,>(data: T) => ({ ok: true as const, data });
export const fail = (status: number, code: string | null = null, info?: Record<string, unknown>) => ({
  ok: false as const,
  status,
  message: "",
  code,
  ...(info ? { info } : {}),
});

export function agent(over: Partial<ClientAgent>): ClientAgent {
  return {
    id: RECEPCION,
    name: "Recepción",
    status: "active",
    is_principal: true,
    channels: [],
    active_version: 3,
    draft_version: null,
    lifecycle: "published",
    pause_reason: null,
    is_default: true,
    visible_state: { code: "serving", tone: "positive", reason: null },
    opens: "overview",
    ...over,
  };
}

export const AGENTS: ClientAgent[] = [
  agent({}),
  agent({
    id: COBROS,
    name: "Cobros",
    is_principal: false,
    is_default: false,
    channels: [
      { id: CH1, display: "+34 600 000 001" },
      { id: CH2, display: "+34 600 000 002" },
    ],
    lifecycle: "paused",
    pause_reason: "no_balance",
    visible_state: { code: "paused", tone: "warn", reason: "no_balance" },
  }),
  agent({
    id: VENTAS,
    name: "Ventas",
    is_principal: false,
    is_default: false,
    active_version: 1,
    lifecycle: "published",
    visible_state: { code: "ready_no_channel", tone: "info", reason: null },
    opens: "channels",
  }),
];

export function header(over: Partial<AgentHeader> = {}): AgentHeader {
  return {
    id: COBROS,
    name: "Cobros",
    lifecycle: "published",
    pause_reason: null,
    visible_state: { code: "serving", tone: "positive", reason: null },
    is_default: false,
    open_conversations: 0,
    paused_by_kind: null,
    paused_origin: null,
    allowed: ["rename", "pause", "archive", "make_default"],
    ...over,
  };
}
