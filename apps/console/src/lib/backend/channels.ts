import type { ClientHealth } from "../backend";
import type { Call } from "../backend";

/**
 * Lane module `channels` (CP-17 WhatsApp · CP-18 templates · CP-19
 * diagnostics). Types mirror
 * `api/console/schemas_channels.py` — channel metadata only, never
 * credentials, never tenant ids. Spread into `backendFor`.
 */

export type ChannelRole = "agent" | "notifications";

/** Spec 022: el catálogo de Commerce Manager enlazado a la cuenta del número. */
export type Catalog = { id: string; name: string | null; checked_at: string | null };
/** «linked» coincide con Meta · «unchecked» no se pudo comprobar · «permission_missing»
 *  la conexión de WhatsApp no trajo el permiso · «none» no hay. */
export type CatalogState = "none" | "linked" | "permission_missing" | "unchecked" | "coexistence";
export type CatalogError = { code: string; message: string | null; at: string | null };
export type CatalogSummary = { id: string; name: string | null; product_count: number | null };
export type CatalogList = { items: CatalogSummary[]; linked_id: string | null };

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
  /** El logotipo de la aplicación del canal. La consola no lo pide al
   *  proveedor —la CSP no lo dejaría— sino a `/api/channel-logo/…`. */
  logo_url: string | null;
  /** Lo que desvincular no consiguió en Meta (`deregister`, `unsubscribe`).
   *  Vacío es «terminado del todo»; con algo, la tarjeta lo dice y reintenta. */
  unlink_pending: string[];
  catalog: Catalog | null;
  catalog_state: CatalogState;
  catalog_error: CatalogError | null;
  /** Las habilidades que conectar este catálogo encendió en el borrador del agente. */
  catalog_skills_added?: string[];
  /** Spec 049 — Instagram / Messenger: the account or Page and why it needs
   *  attention, if it does (with the step to fix it). */
  display_name?: string | null;
  username?: string | null;
  picture_url?: string | null;
  needs_attention?: string | null;
  needs_attention_help?: string | null;
  comments_enabled?: boolean | null;
  comment_public_reply?: string | null;
  /** Spec 063 (2.3): a quién responde. `unset` es «Sin configurar»: no responde a nadie. */
  audience_mode?: "unset" | "team_only" | "everyone";
};

/** Spec 049: Instagram / Messenger this partner may connect. */
export type MetaSocialKind = "instagram" | "messenger";
export type MetaSocialOffer = {
  app_id: string;
  graph_version: string;
  /** Spec 081: `page_config_id` (Instagram only) also asks for the linked
   *  Facebook Page, so the account's direct messages reach the agent. */
  channels: { kind: MetaSocialKind; config_id: string; page_config_id?: string | null }[];
};
export type MetaSocialAccount = { id: string; name: string; username: string | null; picture_url: string | null };
export type MetaSocialConnectResult = {
  status: "connected" | "choose";
  channel: ChannelDetail | null;
  nonce: string | null;
  accounts: MetaSocialAccount[];
  /** Spec 085: the owner's page gets the account's name instead of the channel. */
  display_name?: string | null;
};

export type ChannelsOverview = {
  channels: ChannelDetail[];
  max_channels: number;
  used_channels: number;
  can_connect: boolean;
  roles_required: boolean;
  meta_connected: boolean;
  meta_social?: MetaSocialOffer | null;
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
  /** Spec 016 (R1.2): what the number changed for the client. */
  client_status: "provisioning" | "active" | "paused" | "archived" | (string & {});
  health: ClientHealth;
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
  /** Spec 050: the category Meta announced and applies in about a day. */
  pending_category?: string | null;
  components: Array<Record<string, unknown>>;
  /** Meta's literal rejection text (their verdict on the partner's template). */
  rejection_reason: string | null;
  suggested_action: SuggestedAction;
  last_event_at: string | null;
  /** Spec 075 (R3): why it cannot be edited here, or `null`. The API decides, never the screen. */
  edit_blocker?: TemplateBlocker | (string & {}) | null;
  /** Spec 075: the content already split by the API, what the editor starts from. */
  draft?: TemplateContentOut | null;
  /** Spec 075 (7.1): the fingerprint of the content, sent back on save. */
  version?: string | null;
  /** Spec 075 (4.1): a template Auphere sends by its name, and the variables it may carry. */
  system_variables?: { mode: "exact" | "subset_keep"; variables: string[] } | null;
};

/** Spec 075 (R4): why a template cannot be edited from the console. */
export const TEMPLATE_BLOCKERS = [
  "status",
  "authentication",
  "media_header",
  "header_variable",
  "unsupported_button",
  "url_variable",
  "too_many_buttons",
  "unsupported_component",
] as const;
export type TemplateBlocker = (typeof TEMPLATE_BLOCKERS)[number];

/** Spec 075: `TemplateContentOut` — a template's content as the editor reads it. */
export type TemplateContentOut = {
  category: string | null;
  header_text: string | null;
  body_text: string;
  footer_text: string | null;
  buttons: Array<{ type: string; label: string; url?: string | null; phone_number?: string | null }>;
  examples: Record<string, string>;
};

export type TemplateList = { items: TemplateRow[]; approved: number; rejected: number; pending: number };

export type TemplateButton = { type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER"; label: string; url?: string; phone_number?: string };
export type TemplateCreateBody = {
  name: string;
  language: string;
  category: "MARKETING" | "UTILITY" | "AUTHENTICATION";
  header_text?: string;
  /** Required except with AUTHENTICATION, whose body Meta fixes (spec 077). */
  body_text?: string;
  footer_text?: string;
  buttons?: TemplateButton[];
  /** Example per body variable, as Meta requires to review it. */
  examples?: Record<string, string>;
  /** Spec 077: only with AUTHENTICATION — the copy-code button, ≤ 25 characters. */
  otp_button_text?: string;
  /** Spec 077: only with AUTHENTICATION — 1 to 90; absent, no expiry line. */
  otp_expiration_minutes?: number;
  /** Spec 077: only with AUTHENTICATION — «Por tu seguridad, no lo compartas.» */
  otp_security_recommendation?: boolean;
};
export type TemplateCreated = { id: string | null; name: string; status: string | null; category: string | null };
/** Spec 075: `TemplateEditIn` — the name and the language go in the path, never in the body. */
export type TemplateEditBody = {
  version: string;
  confirm: boolean;
  category?: "MARKETING" | "UTILITY" | "AUTHENTICATION";
  header_text?: string;
  body_text: string;
  footer_text?: string;
  buttons?: TemplateButton[];
  examples?: Record<string, string>;
};
/** `changed: false` — nothing changed, so Meta was not called (3.4). */
export type TemplateEdited = { name: string; language: string; changed: boolean; status: string | null; category: string | null };

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
    disconnectChannel: (ref: string, channelId: string) =>
      call<ChannelDetail>(`${base(ref)}/${enc(channelId)}/disconnect`, { method: "POST" }),
    listCatalogs: (ref: string, channelId: string) => call<CatalogList>(`${base(ref)}/${enc(channelId)}/catalogs`),
    setCatalog: (ref: string, channelId: string, catalogId: string, catalogName?: string) =>
      call<ChannelDetail>(`${base(ref)}/${enc(channelId)}/catalog`, {
        method: "PUT",
        body: catalogName ? { catalog_id: catalogId, catalog_name: catalogName } : { catalog_id: catalogId },
      }),
    clearCatalog: (ref: string, channelId: string) =>
      call<ChannelDetail>(`${base(ref)}/${enc(channelId)}/catalog`, { method: "DELETE" }),
    /** Spec 040: a link the business owner opens on their own device. */
    whatsappSignupLink: (ref: string, mode: "cloud_api" | "coexistence") =>
      call<{ url: string; mode: string; expires_at: string }>(`${base(ref)}/whatsapp/signup-link`, {
        method: "POST",
        body: { mode },
      }),
    /** Spec 085: the same link for Instagram or Messenger; the owner picks how to sign in. */
    metaSocialSignupLink: (ref: string, kind: MetaSocialKind) =>
      call<{ url: string; channel: MetaSocialKind; expires_at: string }>(`${base(ref)}/${kind}/signup-link`, { method: "POST" }),
    /** The client's recent links (owner, 2026-10-20): one works at a time. */
    whatsappSignupLinks: (ref: string) => call<SignupLinkRow[]>(`${base(ref)}/whatsapp/signup-links`),
    revokeWhatsappSignupLink: (ref: string, linkId: string) =>
      call<null>(`${base(ref)}/whatsapp/signup-links/${enc(linkId)}`, { method: "DELETE" }),
    whatsappSignup: (ref: string, body: WhatsAppSignupBody) =>
      call<WhatsAppSignupResult>(`${base(ref)}/whatsapp/signup`, { method: "POST", body }),
    listTemplates: (ref: string) => call<TemplateList>(`${base(ref)}/whatsapp/templates`),
    createTemplate: (ref: string, body: TemplateCreateBody) =>
      call<TemplateCreated>(`${base(ref)}/whatsapp/templates`, { method: "POST", body }),
    deleteTemplate: (ref: string, name: string) =>
      call<{ name: string; deleted: boolean }>(`${base(ref)}/whatsapp/templates/${enc(name)}`, { method: "DELETE" }),
    /** Spec 075: replace one language of a template, by name and language. */
    editTemplate: (ref: string, name: string, language: string, body: TemplateEditBody) =>
      call<TemplateEdited>(`${base(ref)}/whatsapp/templates/${enc(name)}/${enc(language)}`, { method: "PUT", body }),
    /** Spec 049: the code from Facebook Login for Business → the channel. */
    metaSocialConnect: (ref: string, kind: MetaSocialKind, code: string) =>
      call<MetaSocialConnectResult>(`${base(ref)}/${kind}/connect`, { method: "POST", body: { code } }),
    metaSocialComplete: (ref: string, kind: MetaSocialKind, nonce: string, accountId: string) =>
      call<MetaSocialConnectResult>(`${base(ref)}/${kind}/connect/complete`, {
        method: "POST",
        body: { nonce, account_id: accountId },
      }),
    channelDiagnostics: (ref: string) => call<Diagnostics>(`${base(ref)}/diagnostics`),
    channelTestSend: (ref: string, to: string) =>
      call<TestSendResult>(`${base(ref)}/diagnostics/test-send`, { method: "POST", body: { to } }),
  };
}

/** Spec 040: one of the client's links. The token is never shown again. */
export type SignupLinkRow = {
  id: string;
  /** Spec 085: one list for the three channels. */
  channel?: "whatsapp" | "instagram" | "messenger";
  /** Spec 047 (31.5): un enlace por agente puede ir en «WhatsApp login».
   *  Spec 085: Instagram and Messenger are `meta_login`. */
  mode: "coexistence" | "cloud_api" | "whatsapp_login" | "meta_login";
  state: "valid" | "used" | "revoked" | "expired";
  created_at: string;
  expires_at: string;
  consumed_at: string | null;
};
