import { q, type AgentVersion, type Call } from "../backend";

/**
 * Lane module `onboarding` (CP-10 wizard, CP-07 ⌘K, CP-29 notifications).
 * Types mirror `api/console/schemas_onboarding.py` — metadata only, never
 * message bodies, never tenant ids. Spread into `backendFor`.
 */

export type SeedPlaceholder = {
  key: string;
  required: boolean;
  secret: boolean;
  kind: "text" | "number" | "list";
  example: string | null;
};
export type SeedTemplate = {
  name: string;
  display_name: string;
  version: string;
  vertical: string;
  tools_count: number;
  placeholders: SeedPlaceholder[];
};

export type NotificationSeverity = "info" | "warning" | "critical";
export type Notification = {
  id: string;
  kind: string;
  severity: NotificationSeverity;
  data: Record<string, unknown>;
  external_client_ref: string | null;
  read: boolean;
  created_at: string;
};
export type NotificationPage = { items: Notification[]; next_cursor: string | null; unread: number };

export type OnboardingStepKey = "team" | "first_client" | "agent_published" | "channel_connected" | "first_conversation";
export type OnboardingStep = { key: OnboardingStepKey; done: boolean; href: string };
export type Onboarding = {
  steps: OnboardingStep[];
  done_count: number;
  total: number;
  complete: boolean;
  partner_created_at: string;
  activated_at: string | null;
  time_to_first_active_client_seconds: number | null;
};

export function onboardingApi(call: Call) {
  const enc = encodeURIComponent;
  return {
    listSeedTemplates: () => call<SeedTemplate[]>("/console/seed-templates"),
    stageAgentFromSeed: (ref: string, body: { seed_template: string; placeholders: Record<string, unknown> }) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/from-seed`, { method: "POST", body }),

    listNotifications: (p: { unread?: boolean; limit?: number; cursor?: string } = {}) =>
      call<NotificationPage>(`/console/notifications${q(p)}`),
    unreadNotifications: () => call<{ unread: number }>("/console/notifications/unread-count"),
    markNotificationRead: (id: string) => call<Notification>(`/console/notifications/${enc(id)}/read`, { method: "POST" }),
    markAllNotificationsRead: () => call<{ marked: number }>("/console/notifications/read-all", { method: "POST" }),

    onboarding: () => call<Onboarding>("/console/onboarding"),
  };
}
