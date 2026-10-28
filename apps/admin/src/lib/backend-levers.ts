/**
 * Spec 047 (T172, historia 30): the operator's levers on a partner and a client,
 * and the reconciliations (`contracts/admin-api.md` §5 and §7):
 *
 * - the new console, partner by partner (`api/admin/console_v2.py`);
 * - the «Construcción y pruebas» cap and the account currency
 *   (`api/admin/partner_money.py`);
 * - the sovereign restriction of a client and the reconciliations of the ledger
 *   and of Meta (`api/admin/client_controls.py`).
 *
 * Apart from `backend.ts`, like `backend-models.ts`; same `call`, same token.
 * Every write names the operator (`X-Operator-Id`), which the API puts in the
 * platform audit. Server-side only; the types are imported by the screens.
 */

import "server-only";

import { call } from "@/lib/backend";

/** Only euros and dollars (research D26). */
export type Currency = "EUR" | "USD";

/** `amount_micros` in hundred-thousandths of the currency (5_000_000 = 50). */
export type MoneyMicros = { amount_micros: number; currency: Currency };

// ── the new console (55.2, 55.4, 55.5) ──────────────────────────────────────

/** `services/console_v2.py` (`_agents_of`): one row per agent with an active version. */
export type DryRunAgent = {
  tenant_id: string;
  agent_id: string;
  version_id: string;
  same: boolean;
  /** Absent when `reason` says why there was nothing to compare. */
  prompt_identical?: boolean;
  model_pinned?: boolean;
  /** `no_spec`: the version has no AgentSpec yet. */
  reason?: string;
  /** Absent in the reports written before the API named them. */
  agent_name?: string;
  /** Only in the reports (`partner_tenants.client_name`), and it can be null. */
  client_name?: string | null;
};

export type Audience = { mode: string; numbers: string[]; exceptions?: string[] };

/** `services/console_v2.py` (`_audiences_of`): one row per number (channel). */
export type DryRunChannel = {
  tenant_id: string;
  channel_id: string;
  before: Audience;
  after: Audience;
  /** The channel's audience is still `unset`: the migration would write `after`. */
  pending_migration: boolean;
  same: boolean;
  /** The business's number (`provider_identifier`). */
  identifier?: string | null;
  /** Only in the reports, and it can be null. */
  client_name?: string | null;
};

export type DryRunResult = {
  status: "clean" | "diff";
  agents: DryRunAgent[];
  channels: DryRunChannel[];
};

/** `GET …/console-v2/reports`, the newest first (50 at most). */
export type MigrationReport = {
  id: string;
  kind: "dry_run" | "activation";
  status: "clean" | "diff";
  agents: DryRunAgent[];
  channels: DryRunChannel[];
  /** `operator:{email}`. */
  created_by: string;
  /** Why it was run, when the operator said it. */
  reason?: string | null;
  created_at: string;
};

export type ConsoleV2State = {
  version: "v1" | "v2";
  enabled_at: string | null;
  enabled_by: string | null;
};

// ── the partner's money (43.1, 46.5) ────────────────────────────────────────

export type BuildBudgetSaved = { cap: MoneyMicros; month: string };

/** `GET …/build-budget`: this month's «Construcción y pruebas», in the account currency. */
export type BuildBudget = {
  currency: Currency;
  /** The first day of the month, `2026-10-01`. */
  month: string;
  cap: MoneyMicros;
  spent: MoneyMicros;
  /** `warning` from 80 % spent; `exhausted` stops building and testing. */
  state: "ok" | "warning" | "exhausted";
};

/** «Pedir ampliación»: `console:{email}` or `companion:{user_id}`. */
export type BuildBudgetRequest = { requested_by: string; created_at: string };

export type AccountCurrencyChange = {
  currency: Currency;
  changed: boolean;
  from?: Currency;
  fx?: { rate: string; date: string | null; source: string };
  /** What is left of the purchased balance, already converted. */
  purchased_micros?: number;
};

// ── a client (54.6) ─────────────────────────────────────────────────────────

export type SovereignState = { tenant_id: string; enabled: boolean; has_profile?: boolean };

// ── the reconciliations (43.9, 2.6) ─────────────────────────────────────────

/** `services/wallet/ledger.py` (`reconcile`): a bag that does not add up. */
export type LedgerBagDiff = {
  kind: "bag";
  partner_id: string;
  partner_name: string;
  /** The bag's currency. */
  currency: string;
  tenant_id: string;
  tenant_name: string | null;
  /** The stored balance. */
  balance: number;
  /** The sum of its entries. */
  entries: number;
  /** What the last entry says the balance is; null without entries. */
  last_entry: number | null;
};

/** What the account's ledger took for the bags against what the transfers say. */
export type LedgerAccountDiff = {
  kind: "account";
  partner_id: string;
  partner_name: string;
  /** The account's currency. */
  currency: string;
  tenant_name?: null;
  ledger: number;
  transfers: number;
};

export type LedgerDiff = LedgerBagDiff | LedgerAccountDiff;

/** `meta_reconciliation_runs` with a difference: `diff = meta_count − stored_count`. */
export type MetaDiff = {
  tenant_id: string;
  tenant_name: string;
  channel_id: string;
  /** The business's number; null if the channel is gone. */
  identifier: string | null;
  date: string;
  meta_count: number;
  stored_count: number;
  diff: number;
};

export type Reconciliations = { ledger: LedgerDiff[]; meta: MetaDiff[]; since: string };

const op = (operatorId: string) => ({ "X-Operator-Id": operatorId });
const partner = (id: string) => `/admin/partners/${encodeURIComponent(id)}`;

export const leversBackend = {
  /** Which console the partner sees today. */
  consoleV2State: (partnerId: string) => call<ConsoleV2State>(`${partner(partnerId)}/console-v2`),
  consoleV2Reports: (partnerId: string) =>
    call<MigrationReport[]>(`${partner(partnerId)}/console-v2/reports`).then((r) => r ?? []),
  /** The reason is optional for the dry run and asked by the screen for the switch. */
  consoleV2DryRun: (partnerId: string, reason: string | null, operatorId: string) =>
    call<DryRunResult>(`${partner(partnerId)}/console-v2/dry-run`, {
      method: "POST",
      body: reason ? { reason } : {},
      headers: op(operatorId),
    }),
  consoleV2Enable: (partnerId: string, reason: string, operatorId: string) =>
    call<ConsoleV2State>(`${partner(partnerId)}/console-v2/enable`, {
      method: "POST",
      body: { reason },
      headers: op(operatorId),
    }),
  consoleV2Disable: (partnerId: string, reason: string, operatorId: string) =>
    call<ConsoleV2State>(`${partner(partnerId)}/console-v2/disable`, {
      method: "POST",
      body: { reason },
      headers: op(operatorId),
    }),

  buildBudget: (partnerId: string) => call<BuildBudget>(`${partner(partnerId)}/build-budget`),
  setBuildBudget: (partnerId: string, body: { cap: MoneyMicros; reason: string }, operatorId: string) =>
    call<BuildBudgetSaved>(`${partner(partnerId)}/build-budget`, { method: "PUT", body, headers: op(operatorId) }),
  buildBudgetRequests: (partnerId: string) =>
    call<BuildBudgetRequest[]>(`${partner(partnerId)}/build-budget/requests`).then((r) => r ?? []),
  setAccountCurrency: (partnerId: string, body: { currency: Currency; reason: string }, operatorId: string) =>
    call<AccountCurrencyChange>(`${partner(partnerId)}/account-currency`, {
      method: "PUT",
      body,
      headers: op(operatorId),
    }),

  sovereign: (tenantId: string) =>
    call<SovereignState>(`/admin/clients/${encodeURIComponent(tenantId)}/sovereign`, { optional: true }),
  setSovereign: (tenantId: string, body: { enabled: boolean; reason: string }, operatorId: string) =>
    call<SovereignState>(`/admin/clients/${encodeURIComponent(tenantId)}/sovereign`, {
      method: "PUT",
      body,
      headers: op(operatorId),
    }),

  reconciliations: (days: number) => call<Reconciliations>(`/admin/reconciliations?days=${days}`),
};
