import type { Call } from "../backend";
import { q } from "../backend";
import type { Notification, NotificationPage } from "./onboarding";

/**
 * Lane `lite` (spec 030): the client console's calls, all under
 * `/console/lite/*`. None of them carries a client reference — the API takes
 * the client from the verified person, so there is nothing here to pass.
 */
export type LiteMe = {
  user: { email: string; name: string };
  client: { name: string; modules: string[] };
  balance_contact: { kind: "partner" | "auphere"; name: string };
  /** The client's active agents, principal first (spec 030, iteration 3). */
  agents: { id: string; name: string }[];
  channels: { kind: string; connected: boolean }[];
};

/** `GET /console/lite/home` — the Panel of one client (spec 030, R4). Money in cents. */
export type LiteAttentionKind = "waiting" | "balance_out" | "balance_low";
export type LiteHome = {
  spend_month: { total_cents: number; by_agent: { agent_id: string; name: string; cents: number }[] | null } | null;
  conversations: { last_7d: number; prev_7d: number | null; daily: { day: string; count: number }[] } | null;
  waiting: { count: number; first_conversation_id: string | null } | null;
  balance: { assigned: boolean; remaining_cents: number | null; cap_cents: number | null; days_left: number | null } | null;
  attention: { kind: LiteAttentionKind; count: number | null; days_left: number | null }[];
  errors: string[];
};

/** `/console/lite/usage/*` — the Consumo of one client (spec 030, R5). */
export type LiteUsageSummary = {
  balance: LiteHome["balance"];
  month: { spent_cents: number; projection_cents: number | null; conversations: number | null; avg_per_conversation_cents: number | null } | null;
  by_agent: { agent_id: string; name: string; conversations: number; spent_cents: number; share_pct: number }[] | null;
  errors: string[];
};
export type LiteSpend = { currency: string; days: string[]; series_cents: number[]; month_cents: number; projected_cents: number };
export type LiteUsageBucket = { meter: string; source: string; quantity: number; billable_qty: number; records: number };
export type LiteUsageDetail = { since: string; until: string; buckets: LiteUsageBucket[]; totals_by_meter: Record<string, number>; total_records: number };

/** Path of the client's usage CSV (proxied by `/api/lite/usage/export`). */
export const liteUsageCsvPath = (p: { days: number; lang: string }) => `/console/lite/usage/export.csv${q(p)}`;

export function liteApi(call: Call) {
  return {
    liteMe: () => call<LiteMe>("/console/lite/me"),
    liteHome: () => call<LiteHome>("/console/lite/home"),
    liteUsageSummary: () => call<LiteUsageSummary>("/console/lite/usage/summary"),
    liteUsageSpend: (days: number, agent?: string) => call<LiteSpend>(`/console/lite/usage/spend${q({ days, agent })}`),
    liteUsageDetail: (days: number) => call<LiteUsageDetail>(`/console/lite/usage/detail${q({ days })}`),
    liteNotifications: (p: { unread?: boolean; cursor?: string; limit?: number } = {}) =>
      call<NotificationPage>(`/console/lite/notifications${q(p)}`),
    liteUnreadNotifications: () => call<{ unread: number }>("/console/lite/notifications/unread-count"),
    liteReadAllNotifications: () => call<{ marked: number }>("/console/lite/notifications/read-all", { method: "POST" }),
    liteMarkNotificationRead: (id: string) =>
      call<Notification>(`/console/lite/notifications/${encodeURIComponent(id)}/read`, { method: "POST" }),
  };
}
