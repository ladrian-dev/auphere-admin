import type { Call } from "../backend";
import { q } from "../backend";
import type { Notification, NotificationPage } from "./onboarding";
import type { CapacityKind, ReservasMode } from "./reservas";

/**
 * Lane `lite` (spec 030): the client console's calls, all under
 * `/console/lite/*`. None of them carries a client reference — the API takes
 * the client from the verified person, so there is nothing here to pass.
 */
/** Spec 045 (R5.1): the business's week in the canonical shape. An empty day is closed. */
export type LiteWeekday = "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday";
export type LiteBusinessHours = Record<LiteWeekday, { from: string; to: string }[]>;

/** Spec 045 (R5.1): the business's time zone and hours, as `/me` gives them. */
export type LiteBusiness = {
  /** IANA zone, e.g. `America/Santiago`. */
  timezone: string;
  /** `null` when the business has no hours set. */
  hours: LiteBusinessHours | null;
  /** The hours as one sentence in the person's language, or `null`. */
  hours_label: string | null;
};

/**
 * Spec 043 (contract §1): the client's Reservas mode, and in Aforo what kind of
 * business it is — the screens take their words from it (comensales,
 * personas, plazas). `null` without the module.
 */
export type LiteReservasInfo = { mode: ReservasMode; capacity_kind: CapacityKind | null };

export type LiteMe = {
  user: { email: string; name: string };
  client: { name: string; modules: string[] };
  balance_contact: { kind: "partner" | "auphere"; name: string };
  /** The client's active agents, principal first (spec 030, iteration 3). */
  agents: { id: string; name: string }[];
  channels: { kind: string; connected: boolean }[];
  /** Spec 031 (R3.2): the modules in sidebar order — the only source of the order. */
  nav: string[];
  /** Spec 045 (contract §4). */
  business: LiteBusiness;
  /** Spec 043 (contract §1): `null` without the module. */
  reservas: LiteReservasInfo | null;
};

/** Spec 031 (R7.3): one of the person's phones with the Auphere Customers app. */
export type LitePhone = {
  id: string;
  display_name: string;
  platform: "ios" | "android";
  app_version: string;
  last_seen_at: string;
  enrolled_at: string;
  current: boolean;
};

/** `GET /console/lite/home` — the Panel of one client (spec 030, R4). Money in cents. */
export type LiteAttentionKind = "waiting" | "balance_out" | "balance_low";

/**
 * The client's balance (spec 030, R4.4), the same object in `/home` and
 * `/usage/summary`. Spec 045 (contract §3) adds how long it lasts.
 */
export type LiteBalance = {
  assigned: boolean;
  remaining_cents: number | null;
  cap_cents: number | null;
  /** Days it lasts at the last 7 days' pace; `null` without spend. */
  days_left: number | null;
  /** Days left in the month, today included, in the business's zone. Never `null`. */
  month_days_left: number;
  /** Local date (`YYYY-MM-DD`) it runs out at that pace; `null` without spend or allocation. Today when used up. */
  runs_out_on: string | null;
};

export type LiteHome = {
  spend_month: { total_cents: number; by_agent: { agent_id: string; name: string; cents: number }[] | null } | null;
  conversations: { last_7d: number; prev_7d: number | null; daily: { day: string; count: number }[] } | null;
  waiting: { count: number; first_conversation_id: string | null } | null;
  balance: LiteBalance | null;
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
    // Spec 031: the person's phones («Tus teléfonos»).
    litePhones: () => call<LitePhone[]>("/console/lite/phones"),
    liteClosePhone: (id: string) =>
      call<null>(`/console/lite/phones/${encodeURIComponent(id)}`, { method: "DELETE" }),
  };
}
