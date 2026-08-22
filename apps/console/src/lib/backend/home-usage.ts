import type { Call } from "../backend";
import { q } from "../backend";

/**
 * Lane module `home-usage` (CP-08 home, CP-22 usage, CP-24 alerts, CP-25
 * receipts, CP-28 audit). Types mirror `api/console/schemas_home_usage.py`
 * — units only (never cost), never tenant ids, never message bodies.
 * Spread into `backendFor` in `lib/backend.ts`.
 */

export type HomeClients = { active: number; total: number; provisioning: number; paused: number };
export type HomeConversations = { count: number; since: string; until: string };
export type HomeUsage = {
  units: number;
  meter: string;
  cap: number | null;
  percent: number | null;
  projected_month_units: number;
  basis_days: number;
};
export type IncidentIssue = "whatsapp_degraded" | "no_active_agent" | "failed_messages_24h";
export type IncidentClient = {
  external_client_ref: string;
  client_name: string | null;
  issues: IncidentIssue[];
  failed_messages_24h: number;
  href: string;
};
export type HomeIncidents = { count: number; refs: IncidentClient[] };
export type PendingKind = "client_provisioning" | "invitations_pending" | "usage_alerts_unread";
export type PendingItem = {
  kind: PendingKind;
  external_client_ref: string | null;
  client_name: string | null;
  count: number;
  href: string;
};
export type HomePending = { count: number; items: PendingItem[] };
export type Home = {
  clients: HomeClients | null;
  conversations_period: HomeConversations | null;
  usage_units: HomeUsage | null;
  agents_with_incidents: HomeIncidents | null;
  pending_actions: HomePending | null;
  errors: string[];
  generated_in_ms: number;
};

export type UsageMonth = {
  since: string;
  until: string;
  units: number;
  meter: string;
  cap: number | null;
  percent: number | null;
  projected_month_units: number;
  basis_days: number;
  days_in_month: number;
};
export type UsageBucketV2 = {
  external_client_ref: string | null;
  client_name: string | null;
  meter: string;
  source: "channel" | "qa";
  quantity: number;
  billable_qty: number;
  records: number;
};
export type UsageReportV2 = {
  since: string;
  until: string;
  buckets: UsageBucketV2[];
  totals_by_meter: Record<string, number>;
  total_records: number;
  month: UsageMonth;
  unpriced_records: number;
};
export type UsageSeriesPoint = { day: string; by_meter: Record<string, number> };
export type UsageSeries = { since: string; until: string; source: string; meters: string[]; points: UsageSeriesPoint[] };
export type UsageAlerts = {
  cap_messages_month: number | null;
  recipients: string[];
  enabled: boolean;
  month_units: number;
  percent: number | null;
};
export type UsageAlertsInput = { cap_messages_month: number | null; recipients: string[]; enabled: boolean };
export type AuditVocabularyEntry = { action: string; category: string; severity: string; summary: string };
export type AuditVocabulary = { lang: string; entries: AuditVocabularyEntry[] };

export type Wallet = {
  included_remaining: number;
  purchased_remaining: number;
  available: number;
  reserve: number;
  included_expires_at: string | null;
  exhausted: boolean;
};
export type Allocation = { client_ref: string; cap: number; remaining: number };

export type UsageQuery = { days?: number; client?: string; source?: string };
export type AuditQuery = {
  limit?: number;
  cursor?: string;
  actor?: string;
  action?: string;
  client?: string;
  after?: string;
  before?: string;
  lang?: string;
};

/** Backend paths of the streaming/downloadable resources (proxied by route handlers). */
export const usageCsvPath = (p: UsageQuery & { lang?: string }) => `/console/usage/export.csv${q(p)}`;
export const auditCsvPath = (p: AuditQuery) => `/console/audit/export.csv${q(p)}`;
export const receiptDownloadPath = (invoiceId: string) => `/console/billing/receipts/${encodeURIComponent(invoiceId)}/download`;

export function homeUsageApi(call: Call) {
  return {
    home: () => call<Home>("/console/home"),
    usageV2: (p: UsageQuery = {}) => call<UsageReportV2>(`/console/usage${q(p)}`),
    getWallet: () => call<Wallet>("/console/wallet"),
    listAllocations: () => call<Allocation[]>("/console/wallet/allocations"),
    usageSeries: (p: UsageQuery & { meter?: string } = {}) => call<UsageSeries>(`/console/usage/series${q(p)}`),
    usageAlerts: () => call<UsageAlerts>("/console/usage/alerts"),
    setUsageAlerts: (body: UsageAlertsInput) => call<UsageAlerts>("/console/usage/alerts", { method: "PUT", body }),
    auditV2: (p: AuditQuery = {}) =>
      call<{ items: import("../backend").AuditEntry[]; next_cursor: string | null }>(`/console/audit${q(p)}`),
    auditVocabulary: (lang: string) => call<AuditVocabulary>(`/console/audit/vocabulary${q({ lang })}`),
  };
}
