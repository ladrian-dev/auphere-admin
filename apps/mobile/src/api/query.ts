import { focusManager, onlineManager, QueryClient } from "@tanstack/react-query";
import * as Network from "expo-network";
import { AppState, Platform, type AppStateStatus } from "react-native";

import { ApiError } from "./errors";

/**
 * React Query on the phone (spec 031, T027, R5.5, R14.2).
 *
 * - **Focus** is the app coming back to the foreground: what is on screen is
 *   re-read before the person acts on it.
 * - **Online** follows the phone's network: offline, queries keep what they
 *   last loaded (shown as not updated) and mutations wait.
 * - A refusal (4xx) is an answer, not a blip: it is not retried.
 * - Memory only: nothing about a business's customers is written to disk.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        gcTime: 10 * 60_000,
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
      },
      mutations: { retry: false },
    },
  });
}

let wired = false;

/** Tell React Query about the app's foreground and the phone's network. Once per process. */
export function wireQueryManagers(): void {
  if (wired) return;
  wired = true;
  focusManager.setEventListener((setFocused) => {
    const sub = AppState.addEventListener("change", (s: AppStateStatus) => {
      if (Platform.OS !== "web") setFocused(s === "active");
    });
    return () => sub.remove();
  });
  onlineManager.setEventListener((setOnline) => {
    const sub = Network.addNetworkStateListener((state) => {
      setOnline(state.isConnected !== false && state.isInternetReachable !== false);
    });
    return () => sub.remove();
  });
}

/**
 * The inbox changed: its lists, its counts, and Inicio — whose «Necesita tu
 * atención» is the same number as the tab's badge, so both move together.
 */
export function invalidateInbox(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: keys.inboxLists });
  void qc.invalidateQueries({ queryKey: keys.counts });
  void qc.invalidateQueries({ queryKey: keys.home });
}

/**
 * Spec 044, R17.2: something in Reservas changed — the day, the occupancy, the
 * waitlist, Inicio (which counts today's unconfirmed and «Hoy en Reservas» from
 * the same reads) and the contact's next reservation.
 */
export function invalidateReservas(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: keys.reservas });
  void qc.invalidateQueries({ queryKey: ["inbox", "conversation"] });
}

export const keys = {
  me: ["me"] as const,
  appConfig: ["app", "config"] as const,
  home: ["home"] as const,
  usageSummary: ["usage", "summary"] as const,
  usageSpend: (days: number, agent: string | null) => ["usage", "spend", days, agent] as const,
  conversations: (filter: string, q: string, agent: string | null) => ["inbox", "list", filter, q, agent] as const,
  inboxLists: ["inbox", "list"] as const,
  counts: ["inbox", "counts"] as const,
  conversation: (id: string) => ["inbox", "conversation", id] as const,
  thread: (id: string) => ["inbox", "thread", id] as const,
  replies: ["inbox", "replies"] as const,
  tags: ["inbox", "tags"] as const,
  notices: ["phone", "notices"] as const,
  reservas: ["reservas"] as const,
  reservasConfig: ["reservas", "config"] as const,
  reservasRange: (from: string, to: string) => ["reservas", "range", from, to] as const,
  reservasOccupancy: (from: string, to: string) => ["reservas", "occupancy", from, to] as const,
  reservasSlots: (date: string, serviceId: string | null, proId: string | null, partySize: number | null) =>
    ["reservas", "slots", date, serviceId, proId, partySize] as const,
  reservasWaitlist: ["reservas", "waitlist"] as const,
};
