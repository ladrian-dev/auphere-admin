import type { Bag, ClientPanel, ClientRowV2, VisibleState } from "@/lib/backend/client-records";

/** Datos de ejemplo de la lista y del Panel (spec 047), con la forma de la API. */

export const USD = (amount: number) => ({ amount_micros: Math.round(amount * 100_000), currency: "USD" as const });
export const serving: VisibleState = { code: "serving", tone: "positive", pause_reason: null };
export const noChannel: VisibleState = { code: "ready_no_channel", tone: "info", pause_reason: null };

export const bag = (over: Partial<Bag> = {}): Bag => ({
  state: "ok",
  balance: USD(150),
  assigned: USD(200),
  spent: USD(50),
  pct_spent: 25,
  pct_left: 75,
  days_left: 30,
  days_estimable: true,
  alerts: [],
  ...over,
});

export const row = (over: Partial<ClientRowV2> = {}): ClientRowV2 => ({
  external_client_ref: "barberia-cultor",
  name: "Barbería Cultor",
  status: "active",
  timezone: "Europe/Madrid",
  niche: "Barbería de barrio",
  lifecycle: "active",
  attention: { needs: false, reasons: [] },
  agents: [{ agent_id: "a1", name: "Recepción", visible_state: serving }],
  agents_summary: { total: 1, serving: 1, testing: 0, ready_no_channel: 0, draft: 0, paused: 0 },
  bag: bag(),
  allowed: ["edit", "assign_balance", "new_agent", "archive", "delete"],
  ...over,
});

export const panel = (over: Partial<ClientPanel> = {}): ClientPanel => ({
  ref: "barberia-cultor",
  name: "Barbería Cultor",
  niche: "Barbería de barrio",
  lifecycle: "active",
  bag: bag({ balance: USD(6), assigned: USD(16), spent: USD(10), pct_spent: 62.5, pct_left: 37.5, days_left: 4.2 }),
  attention: { needs: false, reasons: [] },
  spend_by_agent: [
    { agent_id: "a1", name: "Citas", spent: USD(8), share_pct: 80 },
    { agent_id: "a2", name: "Ventas", spent: USD(2), share_pct: 20 },
  ],
  month: {
    period_start: "2026-10-01",
    period_end: "2026-10-31",
    conversations: 5,
    handed_to_person: 2,
    resolved_without_person: 3,
    resolved_pct: 60,
    spent: USD(10),
  },
  top_agents: [
    { agent_id: "a1", name: "Citas", visible_state: serving, spent: USD(8), conversations: 4, spend_per_conversation: USD(2), cap: null },
    { agent_id: "a2", name: "Ventas", visible_state: noChannel, spent: USD(2), conversations: 0, spend_per_conversation: null, cap: null },
  ],
  agents_total: 2,
  missing: null,
  read: { job: null, website: null, networks: [] },
  allowed: ["edit", "assign_balance", "new_agent", "archive", "delete"],
  ...over,
});
