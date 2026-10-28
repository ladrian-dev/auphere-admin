/**
 * Tipos puros del dinero de la consola nueva — spec 047, T159 y T160
 * (requisitos 43 a 46 y 55.3; `contracts/console-api.md` §7). Sin imports con
 * efectos: valen para componentes de cliente y para los tests. Reflejan
 * `api/console/client_bags.py` y `api/console/usage_lines.py`. El cliente de la
 * API es `./money.ts`.
 *
 * El dinero viaja como `{amount_micros, currency}`: cien milésimas de la moneda
 * (100 000 = 1 € o 1 USD). Solo hay euros y dólares.
 */
import type { Currency, MoneyValue } from "@nexus/ui";

export type { Currency };
export type Money = MoneyValue;

/** El estado de una bolsa, el mismo cálculo que los avisos (44.5). */
export type BagState = "ok" | "low" | "not_enough" | "empty";

/** `GET /console/wallet/bags`: la bolsa de cada cliente, en su moneda. */
export type BagOut = {
  ref: string;
  balance: Money;
  month_spent: Money;
  /** El saldo con el que empezó el mes más lo asignado durante el mes (44.5). */
  month_base: Money;
  /** Al ritmo de los últimos 7 días; `null` si no hay ritmo para estimarlo. */
  days_left: number | null;
  state: BagState;
  refill_up_to: Money | null;
  /** «Avisarme cuando le quede menos del 20 %» (44.7). */
  alert_low: boolean;
  /** «Pedir saldo» de hoy para este cliente, si ya lo pidió alguien (45.7). */
  requested_at?: string | null;
};

/** `GET /console/wallet`, lo de la consola nueva: la cuenta en su moneda. */
export type AccountWallet = {
  bags_active: boolean;
  account_currency: Currency | null;
  /** Lo que se puede asignar, sin el pool incluido. */
  assignable_micros: number | null;
  in_bags_micros: number | null;
  in_bags_approx: boolean | null;
};

/** `GET /console/wallet/fx?from=&to=`: cuántas unidades de `to` vale una de `from`. */
export type Fx = { rate: string; date: string | null; source: "ECB" };

/** El recibo de una asignación (43.4, 45.2). `fx.rate` va de la moneda de la cuenta a la de la bolsa. */
export type Receipt = {
  client_balance_before: Money;
  assigned: Money;
  debited_from_account: Money;
  fx: Fx;
  client_balance_after: Money;
  account_left: Money;
  /** Queda poco en la cuenta tras asignar (45.4): un aviso ámbar, sin bloquear. */
  warn_low_account: boolean;
};

export type AssignBody = { amount: Money; refill_up_to?: Money | null; alert_low?: boolean };

/** `PUT …/agents/{agent_id}/cap`. */
export type AgentCapOut = { agent_id: string; monthly_cap_micros: number | null; lifecycle: string };

// ── Consumo (requisito 46) ─────────────────────────────────────────────────

export type UsageLine = "conversations" | "meta" | "build" | "companion";
export const USAGE_LINES: readonly UsageLine[] = ["conversations", "meta", "build", "companion"];
export type Payer = "client_bag" | "business_meta" | "auphere" | "account";
export type LineState = "ok" | "warning" | "exhausted";

export type UsageLineOut = {
  line: UsageLine;
  amount: Money;
  payer: Payer;
  approx: boolean;
  /** Solo «Construcción y pruebas»: su tope del mes y su estado. */
  cap?: Money | null;
  state?: LineState | null;
};

export type ClientUsage = {
  ref: string;
  name: string | null;
  /** Lo que le queda, en la moneda de su bolsa; `null` si aún no tiene bolsa. */
  bag: Money | null;
  /** Lo gastado este mes, en la moneda de la cuenta. */
  month_spent: Money;
  days_left: number | null;
  refill_up_to: Money | null;
  /** «Sin saldo» en rojo, con «Asignar saldo» (46.2). */
  empty: boolean;
};

export type UsageSummary = {
  currency: Currency;
  since: string;
  until: string;
  /** «Saldo disponible»: lo que se puede asignar, sin el pool incluido. */
  available: Money;
  in_bags: Money;
  /** «aprox.»: hay bolsas en otra moneda, convertidas al cambio del día. */
  in_bags_approx: boolean;
  month_spend: Money;
  projected: Money;
  lines: UsageLineOut[];
  clients: ClientUsage[];
};

export type UsageDaily = {
  currency: Currency;
  /** «YYYY-MM-DD», en UTC, del más antiguo a hoy. */
  days: string[];
  lines: UsageLine[];
  /** Por partida, un importe por día (cien milésimas, moneda de la cuenta). */
  series: Partial<Record<UsageLine, number[]>>;
  total: number[];
  approx_lines: UsageLine[];
};

export type UsageDetailRow = {
  ref: string;
  agent_id: string | null;
  agent_name?: string | null;
  meter: string;
  line: UsageLine | string | null;
  source: string;
  quantity: number;
  billable_qty: number;
  records: number;
  /** Lo medido que aún no tiene precio. */
  unpriced: number;
};
export type UsageDetail = { since: string; until: string; rows: UsageDetailRow[] };

export type BuildBudget = { cap: Money; spent: Money; remaining: Money; state: LineState; paid_by: "auphere" };

// ── «Repartir tu saldo en bolsas» (55.3, T160) ─────────────────────────────

export type MigrationProposal = { confirmed_at: string | null; clients: { ref: string; amount: Money }[] };
export type MigrationConfirmed = { status: "confirmed"; clients: number };
/** Lo que el partner ajustó: por cliente, en cien milésimas de la moneda de la cuenta. */
export type MigrationAdjust = Record<string, number>;

/** Lo que el modal de asignar necesita leer al abrirse. */
export type BagContext = {
  bag: BagOut;
  /** La cuenta: lo que se puede asignar, en su moneda. */
  available: Money;
  /** El cambio EUR → USD del día, solo si la bolsa y la cuenta van en monedas distintas. */
  eurUsd: Fx | null;
  /** Quien puede comprar saldo ve «Recargar mi cuenta» (45.3). */
  canRecharge: boolean;
  /** El partner aún reparte con los topes de antes: hay que confirmar el reparto (55.3). */
  bagsActive: boolean;
};

/** La lista de bolsas para «Mover»: a quién se puede mover y en qué moneda va cada una. */
export type BagChoice = { ref: string; name: string; currency: Currency };
