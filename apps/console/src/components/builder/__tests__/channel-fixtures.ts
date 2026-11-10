import type { AgentKnowledge, KnowledgeSource } from "@/lib/backend/agent-knowledge-types";
import type { AgentChannels, ChannelChange, ChannelPage } from "@/lib/backend/channel-config-types";

/** Spec 047 (T115, T134) — un número de un agente, su página, su historial y el conocimiento del agente. */

export const REF = "barberia-cultor";
export const RECEPCION = "11111111-1111-4111-8111-111111111111";
export const VENTAS = "33333333-3333-4333-8333-333333333333";
export const CH = "44444444-4444-4444-8444-444444444441";
export const CH2 = "44444444-4444-4444-8444-444444444442";
export const LINK = "55555555-5555-4555-8555-555555555555";
export const DOC = "66666666-6666-4666-8666-666666666661";
export const DOC2 = "66666666-6666-4666-8666-666666666662";

export const ok = <T,>(data: T) => ({ ok: true as const, data });
export const fail = (status: number, code: string | null = null, info?: Record<string, unknown>) => ({
  ok: false as const,
  status,
  message: "",
  code,
  ...(info ? { info } : {}),
});

export function page(over: Partial<ChannelPage> = {}): ChannelPage {
  return {
    id: CH,
    type: "whatsapp",
    identifier: "+34 611 20 48 93",
    status: "active",
    problem_reason: null,
    visible_state: { code: "team_only", tone: "info", reason: null },
    agent: { id: RECEPCION, name: "Recepción" },
    config: {
      audience: { mode: "team_only", test_numbers: ["+34611204893"], exceptions: [] },
      escalation: { recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "+34600000009", email: null, client_user_id: null }], summary: true },
      wait_message: null,
      notify_from: "auphere",
    },
    admin_only_template: false,
    triggers: ["asks_for_human", { custom: "Si pide factura" }],
    checks: [
      { code: "tests_up_to_date", ok: true, level: "warn", fix: null },
      { code: "escalation_recipient", ok: true, level: "warn", fix: null },
    ],
    revision: 3,
    undo_until: null,
    move_targets: [{ id: VENTAS, name: "Ventas" }],
    allowed: ["configure", "move", "pause", "disconnect"],
    ...over,
  };
}

export const HISTORY: ChannelChange[] = [
  {
    id: "77777777-7777-4777-8777-777777777771",
    at: "2026-10-27T09:00:00Z",
    actor: "console:luis@ladrian.studio",
    origin: "console",
    before: {
      audience: { mode: "unset", test_numbers: [], exceptions: [] },
      escalation: { recipients: [], summary: true },
      wait_message: null,
    },
    after: {
      audience: { mode: "team_only", test_numbers: ["+34611204893"], exceptions: [] },
      escalation: { recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "+34600000009" }], summary: true },
      wait_message: null,
    },
    undo_until: null,
    undone_at: null,
  },
  {
    id: "77777777-7777-4777-8777-777777777770",
    at: "2026-10-26T09:00:00Z",
    actor: "system",
    origin: "connect",
    before: null,
    after: { audience: { mode: "unset", test_numbers: [], exceptions: [] }, escalation: { recipients: [], summary: true }, wait_message: null },
    undo_until: null,
    undone_at: null,
  },
];

export function channels(over: Partial<AgentChannels> = {}): AgentChannels {
  return {
    channels: [
      { id: CH, type: "whatsapp", identifier: "+34 611 20 48 93", visible_state: { code: "team_only", tone: "info", reason: null } },
      { id: CH2, type: "whatsapp", identifier: "+34 611 20 48 94", visible_state: { code: "problem", tone: "danger", reason: "coexistence_inactive" } },
    ],
    pending_link: null,
    ...over,
  };
}

export function source(over: Partial<KnowledgeSource> = {}): KnowledgeSource {
  return {
    id: DOC,
    kind: "file",
    title: "Tarifas mayoristas",
    source_url: null,
    mime: "application/pdf",
    size_bytes: 20480,
    status: "indexed",
    error_code: null,
    chunk_count: 4,
    created_by: "luis@ladrian.studio",
    created_at: "2026-10-27T09:00:00Z",
    updated_at: "2026-10-27T09:00:00Z",
    indexed_at: "2026-10-27T09:00:00Z",
    agent_id: RECEPCION,
    removed_at: null,
    restore_until: null,
    ...over,
  };
}

export function knowledge(over: Partial<AgentKnowledge> = {}): AgentKnowledge {
  return { items: [source()], business_sources: 3, ...over };
}
