import "server-only";

import { clientIpHeader } from "./client-ip";
import { env } from "./env";
import { mintPrincipalToken, mintServiceToken } from "./jwt";
import type { Principal } from "./principal";

/**
 * Typed client for the API's ``/console/*`` family (CP-03/CP-04).
 *
 * Written clean — NOT copied from apps/admin. The differences are the
 * point:
 *
 *  - there is no static credential: every call mints a fresh 60-second
 *    EdDSA token for the CURRENT principal (``mintPrincipalToken``);
 *  - the client never sends ``tenant_id``/``partner_id`` — the API does
 *    not accept them, clients are addressed by ``external_client_ref``;
 *  - ``BackendError`` keeps the same three fields as the admin's
 *    (``status``, ``url``, ``body``) so error handling stays interchangeable.
 */
export class BackendError extends Error {
  constructor(
    public readonly status: number,
    public readonly url: string,
    public readonly body: unknown,
  ) {
    super(
      `backend ${status} ${url}: ${
        typeof body === "string" ? body.slice(0, 200) : JSON.stringify(body).slice(0, 200)
      }`,
    );
    this.name = "BackendError";
  }
  /** FastAPI ``detail`` when present — the message a partner should read. */
  get detail(): string {
    const b = this.body as { detail?: unknown } | null;
    if (b && typeof b === "object" && typeof b.detail === "string") return b.detail;
    return this.message;
  }

  /**
   * The closed-vocabulary code when the endpoint answers with a structured
   * ``detail`` — ``{"code": "tier_below_usage", ...}``.
   *
   * Without this, a structured detail falls through to ``message``, which
   * carries the raw JSON of the backend response. Putting that in front of a
   * person is exactly what principle III forbids: the screen writes the
   * sentence, the API only names the case.
   */
  get code(): string | null {
    const b = this.body as { detail?: unknown } | null;
    const detail = b && typeof b === "object" ? b.detail : null;
    if (detail && typeof detail === "object" && typeof (detail as { code?: unknown }).code === "string") {
      return (detail as { code: string }).code;
    }
    return null;
  }

  /** Extra fields the structured detail carried, minus the code. */
  get info(): Record<string, unknown> {
    const b = this.body as { detail?: unknown } | null;
    const detail = b && typeof b === "object" ? b.detail : null;
    if (detail && typeof detail === "object") {
      const rest = { ...(detail as Record<string, unknown>) };
      delete rest.code;
      return rest;
    }
    return {};
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type Opts = { method?: Method; body?: unknown; optional?: boolean; signal?: AbortSignal };

/**
 * La IP del visitante, reenviada a la API.
 *
 * Sin esto la API ve la IP de salida de este BFF para todo el mundo, y su cubo
 * de ritmo «por IP» deja de ser por IP. Se lee de las cabeceras entrantes, que
 * aquí sí pone la plataforma. Si `next/headers` no está disponible —fuera de
 * una petición— no se manda nada y la API cae a su cubo único.
 */
async function forwardedClientIp(): Promise<Record<string, string>> {
  try {
    const { headers } = await import("next/headers");
    return clientIpHeader(await headers());
  } catch {
    return {};
  }
}

async function request<T>(token: string, path: string, opts: Opts = {}): Promise<T | null> {
  const url = `${env().NEXUS_BACKEND_URL}${path}`;
  const res = await fetch(url, {
    method: opts.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(await forwardedClientIp()),
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
    signal: opts.signal,
  });
  if (res.status === 404 && opts.optional) return null;
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) throw new BackendError(res.status, url, parsed);
  return parsed as T;
}

// ── response types (mirror api/console/schemas.py — metadata only) ─────

export type GoogleCallback = {
  outcome: "session" | "signup_pending";
  session_token?: string | null;
  expires_at?: string | null;
  signup_token?: string | null;
};

export type SignupLookup = {
  email: string;
  provider: "google" | null;
  expires_at: string;
};

export type SignupCompleted = {
  session_token: string;
  expires_at: string;
  partner_slug: string;
  role: "owner";
};

export type Quota = {
  max_clients: number;
  used_clients: number;
  remaining_clients: number;
  max_channels_per_client: number;
};
export type Me = {
  user_id: string;
  email: string;
  display_name: string | null;
  role: string;
  permissions: string[];
  membership_id: string;
  partner: { slug: string; name: string; status: string };
  quota: Quota;
  // CO-08 §10 — la bandera del Companion por partner. La puerta real está en
  // el backend (`companion:use` Y la bandera); esto es solo lo que decide si
  // se monta la burbuja. Apagada es AUSENCIA, no un botón gris con tooltip.
  companion_enabled: boolean;
};
export type ClientSummary = {
  external_client_ref: string;
  name: string;
  status: "provisioning" | "active" | "paused" | "archived";
  timezone: string;
  created_at: string;
  updated_at: string;
};
export type ClientHealth = {
  whatsapp_connected: boolean;
  display_phone_number: string | null;
  agent_version: number | null;
  agent_configured: boolean;
  ready: boolean;
  missing: string[];
};
export type Client = ClientSummary & { health: ClientHealth };
export type ClientPage = { items: ClientSummary[]; total: number; limit: number; offset: number };
export type ClientCreated = {
  external_client_ref: string;
  status: string;
  agent_status: string;
  whatsapp_connected: boolean;
  quota: Quota;
};
export type AgentVersion = {
  version: number;
  status: "staged" | "active" | "archived";
  system_prompt: string;
  tools: string[];
  seed_template_ref: string | null;
  created_by: string | null;
  created_at: string;
  promoted_at: string | null;
  promoted_by: string | null;
};
export type AgentBundle = { active_version: number | null; versions: AgentVersion[] };
export type Channel = {
  id: string;
  type: string;
  provider: string;
  provider_identifier: string;
  status: string;
  role: string | null;
  last_health_check_at: string | null;
  created_at: string;
};
export type ConversationMeta = {
  id: string;
  channel_id: string;
  channel_type: string | null;
  status: string;
  agent_active: boolean;
  started_at: string;
  last_activity_at: string;
  turns: number;
  inbound_messages: number;
  outbound_messages: number;
  failed_messages: number;
  escalated: boolean;
  avg_latency_ms: number | null;
  duration_seconds: number | null;
};
export type ConversationPage = { items: ConversationMeta[]; total: number; limit: number; offset: number };
export type ConversationStats = {
  since: string;
  until: string;
  conversations: number;
  open: number;
  escalated: number;
  closed: number;
  turns: number;
  failed_messages: number;
  avg_latency_ms: number | null;
};
export type UsageBucket = {
  external_client_ref: string | null;
  client_name: string | null;
  meter: string;
  source: "channel" | "qa";
  quantity: number;
  billable_qty: number;
  records: number;
};
export type UsageReport = {
  since: string;
  until: string;
  buckets: UsageBucket[];
  totals_by_meter: Record<string, number>;
  total_records: number;
};
export type AuditEntry = {
  id: string;
  at: string;
  actor: string;
  action: string;
  target: string;
  external_client_ref: string | null;
  client_name: string | null;
  summary: string;
};
export type AuditPage = { items: AuditEntry[]; next_cursor: string | null };
export type Member = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  status: string;
  accepted_at: string | null;
  created_at: string;
  is_you: boolean;
};
export type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at: string;
};
export type InvitationCreated = Invitation & { accept_path: string; email_sent: boolean };
export type Team = { members: Member[]; invitations: Invitation[] };
export type InvitationLookup = { partner_name: string; email: string; role: string; expires_at: string };
/** Accepting also opens the session (auto-login) — see `api/console/invitations.py`. */
export type InvitationAccepted = {
  membership_id: string;
  partner: { slug: string; name: string; status: string };
  role: string;
  token: string;
  expires_at: string;
};
/**
 * The principal as the API resolves it (`api/console/schemas_auth.py`).
 * `access` is the whole authorization answer: `ok` renders the console,
 * anything else renders `/no-access`. It is the API's job, not ours — this
 * app has no database to check it against.
 */
export type ApiPrincipal = {
  user_id: string;
  email: string;
  display_name: string | null;
  locale: string;
  access: "ok" | "no_membership" | "suspended" | "disabled";
  membership_id: string | null;
  partner_id: string | null;
  partner_slug: string | null;
  partner_name: string | null;
  partner_status: string | null;
  role: string | null;
  permissions: string[];
  console_enabled: boolean;
};
export type LoginResult = { token: string; expires_at: string; principal: ApiPrincipal };
export type ApiKey = {
  id: string;
  type: "live" | "test";
  prefix_snippet: string;
  scopes: string[];
  allowed_origins: string[];
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  grace_expires_at: string | null;
};
export type ApiKeyCreated = ApiKey & { plaintext: string };
export type ReceiptSummary = {
  invoice_id: string;
  period_year: number;
  period_month: number;
  total_usd: number;
  currency: string;
  status: string;
  issued_at: string | null;
  due_date: string;
};
import type { CancelOut, CheckoutOut, MembershipOut } from "./backend/membership";

export type { CancelOut, CheckoutOut, MembershipOut, TierOut } from "./backend/membership";

export type Billing = { billing_email: string | null; contact_email: string | null; receipts: ReceiptSummary[] };

// ── client factory ─────────────────────────────────────────────────────

/** Query-string builder shared by every lane module. */
export const q = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
};

/** One authenticated call: mints a fresh 60 s token, then requests. */
export type Call = <T>(path: string, opts?: Opts) => Promise<T>;
export type { Opts };

/**
 * Lane modules (``lib/backend/<lane>.ts``) export ``<lane>Api(call)`` and
 * are spread into ``backendFor`` below. Keeps this file from being the
 * merge hotspot of every package.
 */
import { agentToolsApi } from "./backend/agent-tools";
import { channelsApi } from "./backend/channels";
import { companionApi } from "./backend/companion";
import { homeUsageApi } from "./backend/home-usage";
import { onboardingApi } from "./backend/onboarding";
import { playgroundApi } from "./backend/playground";
import { teammatesApi } from "./backend/teammates";
export type { ExecMode, LocalExecCeiling, LocalExecPolicy, LocalExecPref } from "./backend/teammates";
import { workstationApi, workstationPartnerApi } from "./backend/workstation";

/** Mint-per-call function for a principal (also used by route handlers that stream). */
export function callFor(principal: Principal): Call {
  const claims = { userId: principal.userId, partnerId: principal.partnerId, role: principal.role };
  return async <T>(path: string, opts?: Opts): Promise<T> => {
    const token = await mintPrincipalToken(claims);
    return (await request<T>(token, path, opts)) as T;
  };
}

/** Raw token for a principal — ONLY for streaming route handlers that must forward SSE. */
export async function tokenFor(principal: Principal): Promise<string> {
  return mintPrincipalToken({ userId: principal.userId, partnerId: principal.partnerId, role: principal.role });
}

/** A backend client bound to a principal. Every method mints its own token. */
export function backendFor(principal: Principal) {
  const call = callFor(principal);
  const enc = encodeURIComponent;
  return {
    /**
     * El código que lleva ESTA sesión a la app de escritorio (spec 009, R3.1).
     *
     * Va con la credencial de la persona y no con la de servicio: la API lo
     * emite para quien lo pide y para nadie más, así que quién pide tiene que
     * viajar en el token.
     */
    issueSessionCode: (): Promise<{ code: string }> =>
      call<{ code: string }>("/console/auth/session-code", { method: "POST" }),
    // lane modules — each lane owns its file under lib/backend/
    ...agentToolsApi(call),
    ...playgroundApi(call),
    ...channelsApi(call),
    ...companionApi(call),
    ...homeUsageApi(call),
    ...onboardingApi(call),
    ...workstationApi(call),
    ...workstationPartnerApi(call),
    ...teammatesApi(call),

    me: () => call<Me>("/console/me"),

    listClients: (p: { q?: string; status?: string; sort?: string; order?: string; limit?: number; offset?: number } = {}) =>
      call<ClientPage>(`/console/clients${q(p)}`),
    getClient: (ref: string) => call<Client>(`/console/clients/${enc(ref)}`),
    createClient: (body: { external_client_ref: string; name: string; timezone?: string; placeholders?: Record<string, unknown> }) =>
      call<ClientCreated>("/console/clients", { method: "POST", body }),
    updateClient: (ref: string, body: { name?: string; timezone?: string }) =>
      call<Client>(`/console/clients/${enc(ref)}`, { method: "PATCH", body }),
    setClientStatus: (ref: string, status: "active" | "paused" | "archived") =>
      call<Client>(`/console/clients/${enc(ref)}/status`, { method: "POST", body: { status } }),
    deleteClient: (ref: string, confirmName: string) =>
      call<null>(`/console/clients/${enc(ref)}`, { method: "DELETE", body: { confirm_name: confirmName } }),

    getAgent: (ref: string) => call<AgentBundle>(`/console/clients/${enc(ref)}/agent`),
    stageAgentVersion: (ref: string, body: { system_prompt: string; tools?: string[] }) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/versions`, { method: "POST", body }),
    publishAgentVersion: (ref: string, version: number) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/versions/${version}/publish`, { method: "POST" }),
    rollbackAgentVersion: (ref: string, version: number) =>
      call<AgentVersion>(`/console/clients/${enc(ref)}/agent/versions/${version}/rollback`, { method: "POST" }),

    listChannels: (ref: string) => call<Channel[]>(`/console/clients/${enc(ref)}/channels`),
    listConversations: (ref: string, p: { status?: string; escalated?: boolean; with_errors?: boolean; limit?: number; offset?: number } = {}) =>
      call<ConversationPage>(`/console/clients/${enc(ref)}/conversations${q(p)}`),
    conversationStats: (ref: string, days = 30) =>
      call<ConversationStats>(`/console/clients/${enc(ref)}/conversations/stats${q({ days })}`),

    usage: (p: { days?: number; client?: string; source?: string } = {}) => call<UsageReport>(`/console/usage${q(p)}`),
    audit: (p: { limit?: number; cursor?: string; actor?: string; action?: string; client?: string } = {}) =>
      call<AuditPage>(`/console/audit${q(p)}`),

    team: () => call<Team>("/console/team"),
    invite: (body: { email: string; role: string }) => call<InvitationCreated>("/console/team/invitations", { method: "POST", body }),
    revokeInvitation: (id: string) => call<null>(`/console/team/invitations/${enc(id)}`, { method: "DELETE" }),
    changeMemberRole: (id: string, role: string) => call<Member>(`/console/team/members/${enc(id)}/role`, { method: "PATCH", body: { role } }),
    changeMemberStatus: (id: string, status: "active" | "suspended") =>
      call<Member>(`/console/team/members/${enc(id)}/status`, { method: "PATCH", body: { status } }),
    removeMember: (id: string) => call<null>(`/console/team/members/${enc(id)}`, { method: "DELETE" }),

    listKeys: () => call<ApiKey[]>("/console/keys"),
    createKey: (body: { type?: "live" | "test"; scopes?: string[]; allowed_origins?: string[] }) =>
      call<ApiKeyCreated>("/console/keys", { method: "POST", body }),
    rotateKey: (id: string, graceHours = 24) => call<ApiKeyCreated>(`/console/keys/${enc(id)}/rotate`, { method: "POST", body: { grace_hours: graceHours } }),
    revokeKey: (id: string) => call<ApiKey>(`/console/keys/${enc(id)}/revoke`, { method: "POST" }),

    billing: () => call<Billing>("/console/billing"),
    membership: () => call<MembershipOut>("/console/billing/membership"),
    startCheckout: (tier_code: string) =>
      call<CheckoutOut>("/console/billing/checkout", { method: "POST", body: { tier_code } }),
    buyCredit: (amount_cents: number) =>
      call<CheckoutOut>("/console/billing/credit", { method: "POST", body: { amount_cents } }),
    billingPortal: () => call<{ url: string }>("/console/billing/portal"),
    cancelSubscription: () =>
      call<CancelOut>("/console/billing/subscription", { method: "DELETE" }),
  };
}

export type Backend = ReturnType<typeof backendFor>;

/**
 * Pre-session calls: login, session lookup, logout and the two invitation
 * endpoints. All authenticated with the BFF's **service token** (`svc:
 * "console"`), because there is no principal yet — the API mints none of
 * this from the browser, only from this server.
 */
export const consoleService = {
  async lookupInvitation(token: string): Promise<InvitationLookup | null> {
    const t = await mintServiceToken();
    return request<InvitationLookup>(t, `/console/invitations/${encodeURIComponent(token)}`, { optional: true });
  },
  async acceptInvitation(token: string, body: { password: string; display_name?: string | null }): Promise<InvitationAccepted> {
    const t = await mintServiceToken();
    return (await request<InvitationAccepted>(t, `/console/invitations/${encodeURIComponent(token)}/accept`, {
      method: "POST",
      body,
    })) as InvitationAccepted;
  },
  /** 401 → wrong credentials (also: locked account). 429 → too many attempts. */
  async login(body: { email: string; password: string }): Promise<LoginResult> {
    const t = await mintServiceToken();
    return (await request<LoginResult>(t, "/console/auth/login", { method: "POST", body })) as LoginResult;
  },
  /**
   * Canjea el código de un solo uso de la app de escritorio (spec 009, R4).
   *
   * Va con la credencial de **servicio** y no con la de la persona, como el
   * login y la vuelta de Google: quien llega aquí todavía no es nadie. En la
   * API no hay ni una ruta `/console/*` sin credencial, y una suite de
   * aislamiento lo comprueba una por una.
   */
  async redeemSessionCode(body: { code: string }): Promise<{
    session_token: string;
    expires_at: string;
  }> {
    const t = await mintServiceToken();
    return (await request<{ session_token: string; expires_at: string }>(
      t,
      "/console/auth/session-code/redeem",
      { method: "POST", body },
    )) as { session_token: string; expires_at: string };
  },
  /** `null` when the token is unknown or expired — never an exception. */
  async session(token: string): Promise<ApiPrincipal | null> {
    const t = await mintServiceToken();
    try {
      const res = await request<{ principal: ApiPrincipal }>(t, "/console/auth/session", {
        method: "POST",
        body: { token },
      });
      return res?.principal ?? null;
    } catch (err) {
      if (err instanceof BackendError && err.status === 401) return null;
      throw err;
    }
  },
  /**
   * Pide el alta. **Siempre 202**, exista o no el correo: la API no
   * distingue, y esta capa tampoco puede hacerlo sin deshacer el trabajo.
   * `503` es la bandera apagada, y el llamante lo usa para NO pintar el
   * formulario — no para pintar un formulario con un error.
   */
  async startSignup(body: { email: string; locale: "es" | "en" }): Promise<void> {
    const t = await mintServiceToken();
    await request<{ status: "sent" }>(t, "/console/signup", { method: "POST", body });
  },
  /** `null` cuando el enlace está muerto — los cuatro casos son el mismo. */
  async lookupSignup(token: string): Promise<SignupLookup | null> {
    const t = await mintServiceToken();
    return request<SignupLookup>(t, `/console/signup/${encodeURIComponent(token)}`, { optional: true });
  },
  async completeSignup(
    token: string,
    body: { company_name: string; password: string; display_name?: string | null },
  ): Promise<SignupCompleted> {
    const t = await mintServiceToken();
    return (await request<SignupCompleted>(t, `/console/signup/${encodeURIComponent(token)}/complete`, {
      method: "POST",
      body,
    })) as SignupCompleted;
  },
  /**
   * ¿Se puede ofrecer Google? **Nunca lanza y nunca crea nada.**
   *
   * Un fallo del backend aquí significa «no lo sé», y no saberlo se trata como
   * «no hay»: no se anuncia lo que no se puede demostrar. Es un `GET` a un
   * endpoint sin efectos, no `\/start` — ése acuña un PKCE que viviría diez
   * minutos en Redis sin que nadie lo consuma.
   */
  async googleAvailable(): Promise<boolean> {
    try {
      const t = await mintServiceToken();
      const r = await request<{ available: boolean }>(t, "/console/auth/google/available");
      return r?.available === true;
    } catch {
      return false;
    }
  },
  async googleStart(intent: "login" | "signup"): Promise<{ authorization_url: string }> {
    const t = await mintServiceToken();
    return (await request<{ authorization_url: string }>(t, "/console/auth/google/start", {
      method: "POST",
      body: { intent },
    })) as { authorization_url: string };
  },
  async googleCallback(body: { code: string; state: string }): Promise<GoogleCallback> {
    const t = await mintServiceToken();
    return (await request<GoogleCallback>(t, "/console/auth/google/callback", {
      method: "POST",
      body,
    })) as GoogleCallback;
  },
  async logout(token: string): Promise<void> {
    const t = await mintServiceToken();
    await request<null>(t, "/console/auth/logout", { method: "POST", body: { token } });
  },
};
