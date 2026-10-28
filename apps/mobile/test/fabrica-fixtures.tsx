import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import type { AgentCard, BusinessSections, Correction } from "@/api/endpoints";
import { ToastProvider } from "@/ui/toast";

/**
 * Spec 047 (T169, T170, T176): a client with two agents and a small business,
 * as the API sends them (`contracts/lite-app-api.md`), and the providers a
 * screen of the root stack lives in — a real React Query cache, the brief
 * notice and the safe area.
 */
export const AGENT = "11111111-1111-4111-8111-111111111111";
export const AGENT_2 = "22222222-2222-4222-8222-222222222222";
export const CHANNEL = "33333333-3333-4333-8333-333333333333";
export const CONVERSATION = "44444444-4444-4444-8444-444444444444";
export const MESSAGE = "55555555-5555-4555-8555-555555555555";
export const SERVICE = "66666666-6666-4666-8666-666666666666";
export const LOCATION = "77777777-7777-4777-8777-777777777777";
export const SPECIAL = "88888888-8888-4888-8888-888888888888";
export const CHANGE = "99999999-9999-4999-8999-999999999999";

export function agent(over: Partial<AgentCard> = {}): AgentCard {
  return {
    id: AGENT,
    name: "Recepción",
    is_default: true,
    visible_state: { code: "serving", tone: "positive", reason: null },
    pause_reason: null,
    paused_by_kind: null,
    paused_origin: null,
    paused_by_name: null,
    paused_at: null,
    open_conversations: 0,
    channels: [{ id: CHANNEL, type: "whatsapp", identifier: "+56 9 5555 0101", visible_state: { code: "everyone", tone: "positive", reason: null }, allowed: ["pause"] }],
    allowed: ["pause"],
    ...over,
  };
}

export const pausedBySystem = (reason: "no_balance" | "agent_cap" | "client_paused") =>
  agent({
    visible_state: { code: "paused", tone: "warn", reason },
    pause_reason: reason,
    paused_by_kind: reason === "client_paused" ? "partner_member" : "system",
    paused_origin: reason === "client_paused" ? "console" : "system",
    allowed: [],
  });

const shift = (open: string, close: string) => ({ open, close, overnight: false });

export function business(over: Partial<BusinessSections> = {}): BusinessSections {
  const weekday = [shift("09:00", "14:00"), shift("17:00", "20:00")];
  return {
    hours: {
      revision: 4,
      state: "complete",
      allowed: ["edit"],
      location_id: null,
      inherits: false,
      layout: "daily",
      days: { mon: weekday, tue: weekday, wed: weekday, thu: weekday, fri: weekday, sat: [shift("10:00", "14:00")], sun: [] },
      label: "De lunes a viernes de 9:00 a 14:00 y de 17:00 a 20:00, los sábados de 10:00 a 14:00",
    },
    special_dates: {
      revision: 2,
      state: "optional",
      allowed: ["edit"],
      items: [{ id: SPECIAL, name: "Navidad", from: "2026-12-25", to: "2026-12-25", closed: true, shifts: [], location_id: null, archived: false }],
    },
    services: {
      revision: 7,
      state: "complete",
      allowed: ["edit"],
      currency: "CLP",
      exponent: 0,
      agents: [{ id: AGENT, name: "Recepción", serves_all: true }],
      items: [
        {
          id: SERVICE,
          name: "Corte de pelo",
          description: "Lavado incluido.",
          bookable: true,
          duration_min: 30,
          price: { kind: "amount", amount_minor: 15000 },
          currency: "CLP",
          staff: "all",
          agents: { mode: "all_agents", agent_ids: [] },
          used_by: [{ id: AGENT, name: "Recepción" }],
          archived: false,
        },
      ],
    },
    locations: {
      revision: 1,
      state: "complete",
      allowed: ["edit"],
      items: [{ id: LOCATION, name: "Providencia", address: "Av. Providencia 1234", phone_e164: "+56955550101", own_hours: false, label: null, archived: false }],
    },
    provenance: {
      "/hours": { source: "person", by: { kind: "client_user", name: "Marta" }, origin: "app", at: "2026-10-27T10:00:00Z", review: null },
      "/services/x": { source: "web", by: null, origin: null, at: "2026-10-20T10:00:00Z", review: "pending" },
    },
    history: [
      {
        id: CHANGE,
        section: "hours",
        kind: "edit",
        at: "2026-10-28T11:55:00Z",
        by: { kind: "client_user", name: "Marta" },
        origin: "app",
        undone_at: null,
        undoable: true,
      },
    ],
    ...over,
  };
}

export function correction(over: Partial<Correction> = {}): Correction {
  return {
    id: "c0000000-0000-4000-8000-000000000001",
    revision: 1,
    status: "draft",
    kind: "data",
    scope: "business",
    lesson: "El aparcamiento está en la calle de atrás.",
    paraphrase: "Preguntó dónde aparcar.",
    pii: [],
    agent: { id: AGENT, name: "Recepción" },
    applied_change_id: null,
    proposal_id: null,
    created_at: "2026-10-28T12:00:00Z",
    sent_at: null,
    undone_at: null,
    ...over,
  };
}

const metrics = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 47, left: 0, right: 0, bottom: 34 } };

/** A fresh cache per test, never retrying, so a refusal is the answer at once. */
export function testClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
}

export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <SafeAreaProvider initialMetrics={metrics}>
      <QueryClientProvider client={client}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
