import { QueryClient } from "@tanstack/react-query";

/**
 * React Query in the console (spec 082). Only on the screens whose data
 * changes on its own: Reservas (agenda and booking), an agent's Knowledge and
 * the Inbox counters. The first paint still comes from the server
 * (`initialData`); re-reads go through Server Actions — the browser never
 * talks to the API.
 *
 * The same shape as the phone (`apps/mobile/src/api/query.ts`):
 * - **Focus and reconnect** re-read what is older than 15 s (R1.9).
 * - A refusal (4xx) is an answer, not a blip: it is not retried.
 * - Memory only: nothing about a business's customers is written to disk.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        gcTime: 10 * 60_000,
        retry: (count, error) => !(error instanceof ActionError && error.status >= 400 && error.status < 500) && count < 2,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
      },
      mutations: { retry: false },
    },
  });
}

/** A Server Action that answered `{ok:false}`, as a query error. */
export class ActionError extends Error {
  readonly status: number;
  readonly code: string | null;
  constructor(status: number, code?: string | null) {
    super(`action failed: ${status}${code ? ` ${code}` : ""}`);
    this.name = "ActionError";
    this.status = status;
    this.code = code ?? null;
  }
}

type Outcome<T> = { ok: true; data: T } | { ok: false; status: number; code?: string | null };

/** The data of an action's answer, or an `ActionError` for the query to hold. */
export function unwrap<T>(res: Outcome<T>): T {
  if (res.ok) return res.data;
  throw new ActionError(res.status, res.code);
}

/** The keys, by what they read. The roots are what a notice invalidates. */
export const keys = {
  reservas: ["reservas"] as const,
  reservasScreen: (url: string) => ["reservas", "screen", url] as const,
  reservasBooking: (id: string) => ["reservas", "booking", id] as const,
  inbox: ["inbox"] as const,
  inboxCounts: ["inbox", "counts"] as const,
  agentKnowledge: (ref: string, agent: string) => ["agent", ref, agent, "knowledge"] as const,
};
