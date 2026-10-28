import type { AgentConnector, ConnectionPage } from "@/lib/backend/agent-connectors-types";
import type { ModelQuality, PinnableModel, ProfileOption, QualityCheck } from "@/lib/backend/model-quality-types";

/** Spec 047 (T129 y T147) — los datos de prueba de los Conectores de un agente, la página de cada conexión y Calidad. */

export const REF = "barberia-cultor";
export const AGENT = "11111111-1111-4111-8111-111111111111";
export const OTHER_AGENT = "22222222-2222-4222-8222-222222222222";
export const CONN_WOO = "33333333-3333-4333-8333-333333333331";
export const CONN_GCAL = "33333333-3333-4333-8333-333333333332";
export const CONN_COBRO = "33333333-3333-4333-8333-333333333333";
export const JOB = "66666666-6666-4666-8666-666666666666";

export const ok = <T,>(data: T) => ({ ok: true as const, data });
export const fail = (status: number, code: string | null = null, info?: Record<string, unknown>) => ({
  ok: false as const,
  status,
  message: "",
  code,
  ...(info ? { info } : {}),
});
export const noWait = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

export const WOO_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: { store_url: { type: "string", format: "uri", pattern: "^https://" } },
};
export const COBRO_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    business_uuid: { type: "string", minLength: 1 },
    reminders: {
      type: "object",
      additionalProperties: false,
      properties: {
        enabled: { type: "boolean" },
        hour_local: { type: "integer", minimum: 0, maximum: 23 },
      },
    },
  },
};

export function connector(over: Partial<AgentConnector> = {}): AgentConnector {
  return {
    slug: "woocommerce",
    name: "WooCommerce",
    category: "ecommerce",
    logo: null,
    auth_kind: "api_key",
    needed: false,
    connection: null,
    activation: null,
    settings_schema: null,
    ...over,
  };
}

/** El catálogo del agente como lo ordena la API: lo que piden las habilidades primero. */
export function catalog(): AgentConnector[] {
  return [
    connector({
      slug: "woocommerce",
      name: "WooCommerce",
      needed: true,
      connection: { id: CONN_WOO, status: "connected", last_checked_at: "2026-10-28T08:00:00Z" },
      activation: { permission: "read", settings: { store_url: "https://tienda.example" } },
      settings_schema: WOO_SCHEMA,
    }),
    connector({ slug: "googlecalendar", name: "Google Calendar", category: "calendar", auth_kind: "oauth_composio", needed: true }),
    connector({
      slug: "amigable_cobro",
      name: "Amigable Cobro",
      category: "billing",
      connection: { id: CONN_COBRO, status: "connected", last_checked_at: null },
      settings_schema: COBRO_SCHEMA,
    }),
    connector({
      slug: "hubspot",
      name: "HubSpot",
      category: "crm",
      auth_kind: "oauth_composio",
      connection: { id: CONN_GCAL, status: "needs_reauth", last_checked_at: "2026-10-27T20:00:00Z" },
      activation: { permission: "ask_before_write", settings: {} },
    }),
  ];
}

export function connectionPage(over: Partial<ConnectionPage> = {}): ConnectionPage {
  return {
    id: CONN_WOO,
    integration: "woocommerce",
    name: "WooCommerce",
    logo: null,
    status: "connected",
    needs_reauth: false,
    account: "https://tienda.example",
    connected_at: "2026-10-01T10:00:00Z",
    last_checked_at: "2026-10-28T08:00:00Z",
    agents: [
      { agent_id: AGENT, name: "Recepción", permission: "read", settings: { store_url: "https://tienda.example" } },
      { agent_id: OTHER_AGENT, name: "Ventas", permission: "read_write", settings: {} },
    ],
    settings_schema: WOO_SCHEMA,
    ...over,
  };
}

const money = (amount_micros: number) => ({ amount_micros, currency: "USD" as const });
export const NO_CHECK: QualityCheck = { status: "none", job_id: null, reasons: [] };

export function profile(over: Partial<ProfileOption> & Pick<ProfileOption, "profile">): ProfileOption {
  return {
    line: "Línea de la API",
    offered: true,
    price_per_message: money(200),
    delta: money(0),
    current: false,
    certified: true,
    check: NO_CHECK,
    ...over,
  };
}

export function pinnable(over: Partial<PinnableModel> = {}): PinnableModel {
  return {
    deployment: "anthropic/claude-sonnet-eu",
    name: "Claude Sonnet (UE)",
    provider: "Anthropic",
    residency: "eu",
    price_per_message: money(900),
    delta: money(700),
    current: false,
    certified: false,
    check: NO_CHECK,
    ...over,
  };
}

/** «Automático» es la actual; «Económico» está sin comprobar; «Máximo» no pasó. */
export function quality(over: Partial<ModelQuality> = {}): ModelQuality {
  return {
    current: { kind: "profile", profile: "auto" },
    estimate_source: "agent_30d",
    profiles: [
      profile({ profile: "auto", current: true, price_per_message: money(200), delta: money(0) }),
      profile({ profile: "economy", certified: false, price_per_message: money(80), delta: money(-120) }),
      profile({ profile: "balanced", price_per_message: money(420), delta: money(220) }),
      profile({
        profile: "max",
        certified: false,
        price_per_message: money(1500),
        delta: money(1300),
        check: { status: "failed", job_id: JOB, reasons: ["critical_failed", "regression:0.05"] },
      }),
    ],
    pinnable: [pinnable()],
    pinned_line: "…",
    real_price_7d: money(230),
    suggest_auto: false,
    eu_only: false,
    allowed: ["change"],
    ...over,
  };
}
