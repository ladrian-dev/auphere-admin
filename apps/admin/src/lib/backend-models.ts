/**
 * Spec 047 (T150): the API of the model catalog, the router and the
 * certifications (`contracts/admin-api.md` §1–§3). Apart from `backend.ts` so
 * the screens of the ola 6 carry their own types; same `call`, same token.
 *
 * Spec 059 (`specs/059-aparcar-router-y-precios/contracts/admin-api.md`): each
 * row says what uses its model and what it sells for; the way back from a
 * retirement and from «No disponible»; the sale weights and the platform's
 * target multiplier. Decimals travel as strings, as the API writes them.
 *
 * Every write names the operator (`X-Operator-Id`) and carries its reason:
 * the API puts both in the platform audit. Server-side only.
 */

import "server-only";

import { call } from "@/lib/backend";

export type DeploymentStatus =
  | "draft"
  | "certifying"
  | "active"
  | "retiring"
  | "retired"
  | "unavailable"
  | "deprecated";

export type Residency = "eu" | "us" | "global";

export type PriceContract = {
  valid_from: string;
  source: string | null;
  currency: string;
  unit: string;
  input: number | null;
  cache_read: number | null;
  cache_write: number | null;
  output: number | null;
  audio_minute?: number | null;
  image?: number | null;
  long_context_surcharge?: Record<string, unknown>;
};

/** `router-and-catalog.md` §2. */
export type DeploymentContract = {
  id: string;
  model: string;
  family: string | null;
  provider: string;
  route: string | null;
  region: string | null;
  residency: Residency;
  retention: { zero: boolean; how: string | null };
  license: { id: string; url: string | null; read_at: string | null } | null;
  contract: { dpa: boolean; subprocessor_listed: boolean };
  status: DeploymentStatus;
  retire_after: string | null;
  quota: { tpm: number | null; rpm: number | null; verified_at: string | null };
  capabilities: Record<string, unknown>;
  prices: PriceContract[];
  meter_weights: { w_in: number | null; w_cache: number | null; w_out: number | null };
};

/** Why the API could not check the worker's models (research D2). */
export type ModelUsesProblem = "no_heartbeat" | "unpublished" | "mismatch" | "api_outdated";

/** §1: what uses a model. `defaults` is an open list of the registry's uses. */
export type ModelUses = {
  defaults: string[];
  agents: number;
  clients: string[];
  verified: boolean;
  problem: ModelUsesProblem | null;
};

export type SaleLaneKey = "input" | "cache_read" | "output";

/** One lane, per million tokens: cost, weight, sale (`weight × sell`) and `sale ÷ cost`. */
export type SaleLane = {
  cost: string | null;
  weight: string | null;
  sale: string | null;
  multiplier: string | null;
};

/** `unknown`: the target cannot be read and nothing sinks under the floor (4.7). */
export type SaleState =
  | "on_target"
  | "drift"
  | "below_floor"
  | "unweighted"
  | "per_minute"
  | "no_cost"
  | "unknown";

/** §1: what the partner pays for a model. Per minute, or without cost, there are no lanes to propose. */
export type SaleInfo = {
  state: SaleState;
  lanes: Partial<Record<SaleLaneKey, SaleLane>> | null;
  proposed: Record<SaleLaneKey, string> | null;
};

/** §1 and §7: `multiplier` is `null` when the setting cannot be read (4.7). */
export type SalePolicy = {
  multiplier: string | null;
  floor: string;
  sell_usd_per_million: string;
};

export type DeploymentRow = {
  uuid: string;
  display_name: string | null;
  deployment: DeploymentContract;
  current_price: PriceContract | null;
  certified_tasks: string[];
  activation_missing: string[];
  activation_messages: Record<string, string>;
  uses: ModelUses;
  sale: SaleInfo;
  /** The agents still answering with a model whose retirement day came (1.8). */
  retirement_blocked_agents: number | null;
};

export type DeploymentList = { items: DeploymentRow[]; statuses: DeploymentStatus[]; sale_policy: SalePolicy };

/**
 * Spec 059: the panel and the API do not deploy in the same instant (Vercel and
 * ECS). An older API sends no `uses`, `sale` nor `sale_policy`: the panel fills
 * them without claiming anything it does not know — the use stays «not verified»
 * and the sale «without a target».
 */
export function normalizeRow(row: DeploymentRow): DeploymentRow {
  return {
    ...row,
    // `api_outdated` (panel only): that API does not protect, so the panel treats
    // the model as in use and offers no destructive action.
    uses: row.uses ?? { defaults: [], agents: 0, clients: [], verified: false, problem: "api_outdated" },
    sale: row.sale ?? { state: "unknown", lanes: null, proposed: null },
    retirement_blocked_agents: row.retirement_blocked_agents ?? null,
  };
}

export function normalizeList(list: DeploymentList): DeploymentList {
  return {
    ...list,
    items: list.items.map(normalizeRow),
    sale_policy: list.sale_policy ?? { multiplier: null, floor: "1.5", sell_usd_per_million: "10" },
  };
}

/** §6: the three weights, or none; decimals greater than zero. */
export type WeightsIn = { input: string; cache_read: string; output: string; reason: string };

/** §7. */
export type SalePolicyIn = { multiplier: string; apply_to_all: boolean; reason: string };

export type DeploymentIn = {
  id: string;
  display_name: string;
  model: string;
  family?: string | null;
  provider: string;
  route?: string | null;
  region?: string | null;
  residency: Residency;
  retention: { zero: boolean; how: string | null };
  license: { id: string; url: string | null; read_at: string | null } | null;
  contract: { dpa: boolean; subprocessor_listed: boolean };
  capabilities: Record<string, unknown>;
  reason: string;
};

export type PriceIn = {
  valid_from: string;
  input?: number;
  cache_read?: number;
  cache_write?: number;
  output?: number;
  audio_minute?: number;
  source: string;
  currency: string;
};

export type ProposalOut = {
  tenant_id: string;
  agent_id: string;
  client_ref: string | null;
  agent: string;
  /** The substitute's key, or `auto` («Automático»). */
  proposed: string;
};

export type RouterTask = { code: string; conversation: boolean; needs: string[] };

export type TaskPolicyJson = {
  min_quality?: number;
  max_cost_per_call_micros?: number | null;
  escalate_to?: string | null;
  reasoning?: string;
  judge_sampling?: string | number | null;
  reserve?: string | null;
};

export type ProfilePolicyJson = {
  tasks: Record<string, TaskPolicyJson>;
  turn_cost_ceiling_micros?: number | null;
  max_calls_per_turn?: number;
  max_escalations_per_hour?: number;
  latency_p95_ms?: Record<string, number>;
  [key: string]: unknown;
};

export type RouterProfile = {
  profile: string;
  version: number;
  policy: ProfilePolicyJson;
  published_by: string;
  reason: string | null;
  published_at: string;
};

export type RouterPreview = {
  task: string;
  conversation: boolean;
  profile: string;
  policy_version: number;
  outcome: "routed" | "pinned" | "agent_pinned" | "reserve_model" | "no_model";
  chain: { deployment: string; provider: string; residency: Residency; price: PriceContract | null }[];
  rejected: { deployment: string; reason: string }[];
  estimated_cost_micros: number | null;
  facts: {
    eu_only: boolean;
    sovereign: boolean;
    partner_allowed: string[];
    agent_certified: string[];
    degraded: boolean;
  };
};

export type RouterAnomaly = {
  tenant_id: string;
  tenant_name: string;
  task: string;
  kind: "reserve_model" | "no_model" | "cooldown" | "missing_task";
  decision_id: string | null;
  created_at: string;
};

export type RouterAnomalies = {
  items: RouterAnomaly[];
  waiting_no_model: { tenant_id: string; tenant_name: string; conversations: number }[];
  since: string;
};

export type ClassCertification = {
  deployment: string;
  task: string;
  battery_version: number;
  quality: number;
  passed: boolean;
  scores: Record<string, unknown>;
  certified_at: string;
  invalidated_at: string | null;
};

export type AgentCertification = {
  tenant_id: string;
  tenant_name: string;
  agent_id: string;
  agent_name: string;
  deployment: string;
  agent_config_id: string;
  suite_revision: number;
  passed: boolean;
  paid_by: "partner" | "auphere";
  result: Record<string, unknown>;
  certified_at: string;
  invalidated_at: string | null;
};

export type Certifications = {
  by_deployment: ClassCertification[];
  by_agent: AgentCertification[];
  battery_version: number | null;
};

export type Battery = {
  version: number;
  cases: number;
  sources: Record<string, number>;
  weights: Record<string, number>;
  threshold: number;
  coverage_gaps: string[];
};

const op = (operatorId: string) => ({ "X-Operator-Id": operatorId });

function query(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams(
    Object.entries(params).filter((e): e is [string, string] => Boolean(e[1])),
  ).toString();
  return q ? `?${q}` : "";
}

export const modelsBackend = {
  listDeployments: (filters: { status?: string; provider?: string; task?: string } = {}) =>
    call<DeploymentList>(`/admin/models/deployments${query(filters)}`).then((list) =>
      list === null ? null : normalizeList(list),
    ),
  createDeployment: (body: DeploymentIn, operatorId: string) =>
    call<DeploymentRow>("/admin/models/deployments", {
      method: "POST",
      body,
      headers: op(operatorId),
    }),
  activate: (uuid: string, reason: string, operatorId: string) =>
    call<DeploymentRow>(`/admin/models/deployments/${uuid}/activate`, {
      method: "POST",
      body: { reason },
      headers: op(operatorId),
    }),
  /** §3: no notice to the partners any more; a date before today is `422 in_the_past`. */
  addPrice: (uuid: string, body: PriceIn, operatorId: string) =>
    call<{ deployment: DeploymentRow }>(`/admin/models/deployments/${uuid}/prices`, {
      method: "POST",
      body,
      headers: op(operatorId),
    }),
  retire: (uuid: string, body: { retire_after: string; reason: string }, operatorId: string) =>
    call<{ deployment: DeploymentRow; proposals: ProposalOut[] }>(
      `/admin/models/deployments/${uuid}/retire`,
      { method: "POST", body, headers: op(operatorId) },
    ),
  unavailable: (uuid: string, reason: string, operatorId: string) =>
    call<DeploymentRow>(`/admin/models/deployments/${uuid}/unavailable`, {
      method: "POST",
      body: { reason },
      headers: op(operatorId),
    }),
  /** §4: `retiring → active`. */
  cancelRetirement: (uuid: string, reason: string, operatorId: string) =>
    call<DeploymentRow>(`/admin/models/deployments/${uuid}/cancel-retirement`, {
      method: "POST",
      body: { reason },
      headers: op(operatorId),
    }),
  /** §5: `unavailable →` the state it had before. */
  restore: (uuid: string, reason: string, operatorId: string) =>
    call<DeploymentRow>(`/admin/models/deployments/${uuid}/restore`, {
      method: "POST",
      body: { reason },
      headers: op(operatorId),
    }),
  /** §6: in force when saved, without telling the partners. */
  putWeights: (uuid: string, body: WeightsIn, operatorId: string) =>
    call<DeploymentRow>(`/admin/models/deployments/${uuid}/weights`, {
      method: "PUT",
      body,
      headers: op(operatorId),
    }),
  /** §7. */
  getSalePolicy: () => call<SalePolicy>("/admin/models/sale-policy"),
  putSalePolicy: (body: SalePolicyIn, operatorId: string) =>
    call<{ sale_policy: SalePolicy; applied_to: string[] }>("/admin/models/sale-policy", {
      method: "PUT",
      body,
      headers: op(operatorId),
    }),

  taxonomy: () => call<{ version: number; tasks: RouterTask[] }>("/admin/router/taxonomy"),
  profiles: () =>
    call<{ items: RouterProfile[]; ceilings: Record<string, number> }>("/admin/router/profiles"),
  profileVersions: (profile: string) =>
    call<RouterProfile[]>(`/admin/router/profiles/${encodeURIComponent(profile)}/versions`),
  saveProfile: (profile: string, body: { policy: ProfilePolicyJson; reason: string }, operatorId: string) =>
    call<RouterProfile>(`/admin/router/profiles/${encodeURIComponent(profile)}`, {
      method: "PUT",
      body,
      headers: op(operatorId),
    }),
  preview: (body: { tenant_id: string; agent_id?: string; task: string; profile?: string }) =>
    call<RouterPreview>("/admin/router/preview", { method: "POST", body }),
  anomalies: (since?: string) => call<RouterAnomalies>(`/admin/router/anomalies${query({ since })}`),

  certifications: (filters: { deployment?: string; task?: string; agent?: string } = {}) =>
    call<Certifications>(`/admin/certifications${query(filters)}`),
  batteries: () => call<{ items: Battery[] }>("/admin/certifications/batteries"),
  launchCertification: (
    body: { deployment_id: string; tasks?: string[]; agent_ids?: string[] },
    operatorId: string,
  ) =>
    call<{ jobs: { job_id: string }[] }>("/admin/certifications/runs", {
      method: "POST",
      body,
      headers: op(operatorId),
    }),
};
