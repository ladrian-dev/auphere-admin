import type { Call } from "../backend";

/**
 * Lane module `channels` (CP-17 WhatsApp · CP-18 templates · CP-19
 * diagnostics). Types mirror
 * `api/console/schemas_channels.py` — channel metadata only, never
 * credentials, never tenant ids. Spread into `backendFor`.
 */

export type ChannelRole = "agent" | "notifications";

export type ChannelDetail = {
  id: string;
  type: string;
  provider: string;
  provider_identifier: string;
  status: "active" | "paused" | "degraded" | "disconnected" | string;
  role: ChannelRole | null;
  last_health_check_at: string | null;
  created_at: string;
  quality_rating: string | null;
  messaging_tier: string | null;
  verified_name: string | null;
  mode: string | null;
  agent_enabled: boolean;
};

export type ChannelsOverview = {
  channels: ChannelDetail[];
  max_channels: number;
  used_channels: number;
  can_connect: boolean;
  roles_required: boolean;
  meta_connected: boolean;
};

export type WhatsAppSignupBody = {
  code: string;
  waba_id: string;
  phone_number_id?: string;
  business_id?: string;
  mode: "cloud_api" | "coexistence";
};

export type WhatsAppSignupResult = {
  status: string;
  channel_id: string;
  display_phone_number: string;
  mode: string;
  used_channels: number;
  max_channels: number;
};

export const SUGGESTED_ACTIONS = [
  "fix_format",
  "change_category",
  "rewrite_content",
  "remove_promotional",
  "add_variables_samples",
  "contact_support",
  "wait_review",
  "none",
] as const;
export type SuggestedAction = (typeof SUGGESTED_ACTIONS)[number];

export type TemplateRow = {
  id: string | null;
  name: string;
  language: string;
  category: string | null;
  status: string | null;
  quality_score: string | null;
  components: Array<Record<string, unknown>>;
  /** Meta's literal rejection text (their verdict on the partner's template). */
  rejection_reason: string | null;
  suggested_action: SuggestedAction;
  last_event_at: string | null;
};

export type TemplateList = { items: TemplateRow[]; approved: number; rejected: number; pending: number };

export type TemplateButton = { type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER"; label: string; url?: string; phone_number?: string };
export type TemplateCreateBody = {
  name: string;
  language: string;
  category: "MARKETING" | "UTILITY" | "AUTHENTICATION";
  header_text?: string;
  body_text: string;
  footer_text?: string;
  buttons?: TemplateButton[];
};
export type TemplateCreated = { id: string | null; name: string; status: string | null; category: string | null };

export const DIAGNOSTIC_KEYS = [
  "credentials",
  "channel",
  "roles",
  "webhook",
  "health_check",
  "quality",
  "messaging_tier",
  "templates",
  "billing",
] as const;
export type DiagnosticKey = (typeof DIAGNOSTIC_KEYS)[number];
export const WHAT_TO_DO = [
  "connect_whatsapp",
  "reconnect_whatsapp",
  "assign_roles",
  "check_webhook",
  "wait_health_check",
  "review_templates",
  "create_template",
  "improve_quality",
  "check_meta_billing",
  "activate_channel",
  "none",
] as const;
export type WhatToDo = (typeof WHAT_TO_DO)[number];
export type DiagnosticState = "ok" | "warn" | "fail" | "unknown";
export type DiagnosticRow = { key: DiagnosticKey | string; state: DiagnosticState; what_to_do: WhatToDo; detail: string | null; link: string | null };
export type Diagnostics = { rows: DiagnosticRow[]; checked_at: string; healthy: boolean };
export type TestSendResult = { status: string; wamid: string; to: string };

export function channelsApi(call: Call) {
  const enc = encodeURIComponent;
  const base = (ref: string) => `/console/clients/${enc(ref)}/channels`;
  return {
    channelsOverview: (ref: string) => call<ChannelsOverview>(`${base(ref)}/overview`),
    setChannelRole: (ref: string, channelId: string, role: ChannelRole | null) =>
      call<ChannelDetail>(`${base(ref)}/${enc(channelId)}/role`, { method: "PATCH", body: { role } }),
    whatsappSignup: (ref: string, body: WhatsAppSignupBody) =>
      call<WhatsAppSignupResult>(`${base(ref)}/whatsapp/signup`, { method: "POST", body }),
    listTemplates: (ref: string) => call<TemplateList>(`${base(ref)}/whatsapp/templates`),
    createTemplate: (ref: string, body: TemplateCreateBody) =>
      call<TemplateCreated>(`${base(ref)}/whatsapp/templates`, { method: "POST", body }),
    deleteTemplate: (ref: string, name: string) =>
      call<{ name: string; deleted: boolean }>(`${base(ref)}/whatsapp/templates/${enc(name)}`, { method: "DELETE" }),
    channelDiagnostics: (ref: string) => call<Diagnostics>(`${base(ref)}/diagnostics`),
    channelTestSend: (ref: string, to: string) =>
      call<TestSendResult>(`${base(ref)}/diagnostics/test-send`, { method: "POST", body: { to } }),
  };
}
