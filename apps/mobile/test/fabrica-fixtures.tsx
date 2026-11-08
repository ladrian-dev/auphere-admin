import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import type { Correction } from "@/api/endpoints";
import { ToastProvider } from "@/ui/toast";

/**
 * Spec 047 (T170, T176): an agent's correction and the ids of its notices, as
 * the API sends them (`contracts/lite-app-api.md`), and the providers a screen
 * of the root stack lives in — a real React Query cache, the brief notice and
 * the safe area. Agentes and Negocio left the app (spec 056, 2.6), and their
 * agent cards and business sections with them.
 */
export const AGENT = "11111111-1111-4111-8111-111111111111";
export const CHANNEL = "33333333-3333-4333-8333-333333333333";
export const CONVERSATION = "44444444-4444-4444-8444-444444444444";
export const MESSAGE = "55555555-5555-4555-8555-555555555555";

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
