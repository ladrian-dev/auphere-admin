import "server-only";

import { q, type Call } from "../backend";
import type {
  AccountWallet,
  AgentCapOut,
  AssignBody,
  BagOut,
  BuildBudget,
  Currency,
  Fx,
  MigrationAdjust,
  MigrationConfirmed,
  MigrationProposal,
  Money,
  Receipt,
  UsageDaily,
  UsageDetail,
  UsageLine,
  UsageSummary,
} from "./money-types";

/**
 * Spec 047 (T159, T160) — el dinero de la consola nueva: las bolsas de los
 * clientes, asignar, bajar, mover, el relleno, la moneda, «Pedir saldo», el tope
 * del agente, Consumo por partidas y «Repartir tu saldo en bolsas».
 * `contracts/console-api.md` §7.
 *
 * Lo que mueve dinero lleva su `Idempotency-Key`: la pantalla la genera una vez
 * por intento, y un doble clic o un reintento no aparta dos veces.
 */
export function moneyApi(call: Call) {
  const enc = encodeURIComponent;
  const bag = (ref: string) => `/console/clients/${enc(ref)}/bag`;
  const idem = (key: string) => ({ "Idempotency-Key": key });
  return {
    getAccount: () => call<AccountWallet>("/console/wallet"),
    listBags: () => call<BagOut[]>("/console/wallet/bags"),
    getFx: (from: Currency, to: Currency) => call<Fx>(`/console/wallet/fx${q({ from, to })}`),
    assignBalance: (ref: string, body: AssignBody, key: string) =>
      call<Receipt>(`${bag(ref)}/assign`, { method: "POST", body, headers: idem(key) }),
    lowerBalance: (ref: string, amount: Money, key: string) =>
      call<BagOut>(`${bag(ref)}/lower`, { method: "POST", body: { amount }, headers: idem(key) }),
    moveBalance: (fromRef: string, toRef: string, amount: Money, key: string) =>
      call<BagOut[]>("/console/wallet/bags/move", { method: "POST", body: { from_ref: fromRef, to_ref: toRef, amount }, headers: idem(key) }),
    setRefill: (ref: string, upTo: Money | null) => call<BagOut>(`${bag(ref)}/refill`, { method: "PUT", body: { up_to: upTo } }),
    setBagCurrency: (ref: string, currency: Currency, confirm: boolean) =>
      call<BagOut>(`${bag(ref)}/currency`, { method: "PUT", body: { currency, confirm } }),
    requestBalance: (ref: string, note: string | null) =>
      call<{ status: string }>(`${bag(ref)}/request`, { method: "POST", body: note ? { note } : {} }),
    setAgentCap: (ref: string, agentId: string, cap: Money | null) =>
      call<AgentCapOut>(`/console/clients/${enc(ref)}/agents/${enc(agentId)}/cap`, { method: "PUT", body: { monthly_cap: cap } }),

    usageSummary: () => call<UsageSummary>("/console/usage/summary"),
    usageDaily: (params: { days: number; client?: string; line?: UsageLine }) => call<UsageDaily>(`/console/usage/daily${q(params)}`),
    usageDetail: (params: { days: number; client?: string }) => call<UsageDetail>(`/console/usage/detail${q(params)}`),
    buildBudget: () => call<BuildBudget>("/console/usage/build-budget"),
    requestBuildExtension: () => call<{ status: string }>("/console/usage/build-budget/extension-request", { method: "POST" }),

    getMigration: () => call<MigrationProposal>("/console/wallet/migration"),
    confirmMigration: (adjust?: MigrationAdjust) =>
      call<MigrationConfirmed>("/console/wallet/migration/confirm", { method: "POST", body: adjust && Object.keys(adjust).length ? { adjust } : {} }),
  };
}
