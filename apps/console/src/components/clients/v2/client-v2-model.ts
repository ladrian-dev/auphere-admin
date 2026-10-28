import type { MessageKey } from "@/i18n/messages";
import type {
  AgentsSummary,
  Attention,
  AttentionCode,
  Bag,
  ClientAction,
  ClientAgent,
  ClientFilter,
  ClientPanel,
  Lifecycle,
  Money,
  MissingSection,
  VisibleState,
} from "@/lib/backend/client-records";

/**
 * Spec 047 (T065, T067) — lo que la lista y el Panel del cliente pintan, sin
 * React. La API decide (la regla de atención, el estado visible, los días y lo
 * permitido); aquí solo se ponen las palabras y los enlaces.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const COUNTED: ReadonlySet<AttentionCode> = new Set([
  "channel_problem",
  "integration_reauth",
  "agent_cap",
  "agent_without_channel",
]);

/** «Pausado · cliente archivado», «Atendiendo»… de `visible_state`. */
export function agentStateText(t: T, state: VisibleState): string {
  if (state.code === "paused") {
    const reason = state.pause_reason ? t(`clients.v2.pause.${state.pause_reason}` as MessageKey) : t("clients.v2.pause.manual");
    return t("clients.v2.agent.paused", { reason });
  }
  return t(`clients.v2.agent.${state.code}` as MessageKey);
}

/** El motivo de un cliente: el más grave, con su cuenta o sus días. */
export function reasonText(t: T, code: AttentionCode, count: number, bag: Bag | null): string {
  if (code === "low_balance") {
    return bag?.days_left != null ? t("clients.v2.attention.low_balance.days", { days: Math.round(bag.days_left) }) : t("clients.v2.attention.low_balance");
  }
  if (COUNTED.has(code)) {
    return t(`clients.v2.attention.${code}.${count === 1 ? "one" : "other"}` as MessageKey, { n: count });
  }
  return t(`clients.v2.attention.${code}` as MessageKey);
}

export type StateView = { label: string; tone: "danger" | "warn" | "info" | "muted" | "positive"; more: string[] };

/**
 * El tono de cada motivo, como el prototipo (`clientes.md` §1.5): sin saldo en
 * rojo, saldo bajo en ámbar, agentes sin canal en azul, sin agentes en gris. Los
 * motivos que solo tiene la consola van con su gravedad: canal con problemas en
 * rojo, conector por reconectar y tope en ámbar.
 */
const REASON_TONE: Record<AttentionCode, StateView["tone"]> = {
  no_balance: "danger",
  channel_problem: "danger",
  low_balance: "warn",
  integration_reauth: "warn",
  agent_cap: "warn",
  agent_without_channel: "info",
  no_agents: "muted",
};

/** Lo de los agentes ya lo dice su columna (Andrés, 2026-10-28). */
const AGENT_REASONS: ReadonlySet<AttentionCode> = new Set(["no_agents", "agent_without_channel", "agent_cap"]);

/**
 * La columna «Estado»: archivado o en pausa, o el motivo más grave del
 * cliente, o «Al día». Los motivos de sus agentes no cuentan aquí.
 */
export function stateView(t: T, lifecycle: Lifecycle, attention: Attention | null, bag: Bag | null): StateView {
  if (lifecycle === "archived") return { label: t("clients.v2.lifecycle.archived"), tone: "muted", more: [] };
  if (lifecycle === "paused") return { label: t("clients.v2.lifecycle.paused"), tone: "warn", more: [] };
  const [top, ...rest] = (attention?.reasons ?? []).filter((r) => !AGENT_REASONS.has(r.code));
  if (!top) return { label: t("clients.v2.ok"), tone: "positive", more: [] };
  return {
    label: reasonText(t, top.code, top.count, bag),
    tone: REASON_TONE[top.code] ?? "warn",
    more: rest.map((r) => reasonText(t, r.code, r.count, bag)),
  };
}

/** Los agentes que cuentan en la lista: todos menos los archivados. */
export function liveAgents(agents: readonly ClientAgent[]): ClientAgent[] {
  return agents.filter((a) => a.visible_state.code !== "archived");
}

/**
 * «3 agentes · 1 en prueba · 1 pausado» (prototipo §2.3, con plurales): el
 * total y, cuando los hay, los que están en prueba, en pausa o en borrador. Los
 * listos sin canal no suman texto. Sin el resumen de la API, se cuentan.
 */
export function agentsText(t: T, summary: AgentsSummary | null, agents: readonly ClientAgent[]): string {
  const s = summary ?? countAgents(agents);
  if (!s.total) return t("clients.v2.agents.none");
  const parts = [t(s.total === 1 ? "clients.proto.agents.one" : "clients.proto.agents.other", { n: s.total })];
  if (s.testing) parts.push(t("clients.proto.agents.testing", { n: s.testing }));
  if (s.paused) parts.push(t(s.paused === 1 ? "clients.proto.agents.paused.one" : "clients.proto.agents.paused.other", { n: s.paused }));
  if (s.draft) parts.push(t(s.draft === 1 ? "clients.proto.agents.draft.one" : "clients.proto.agents.draft.other", { n: s.draft }));
  return parts.join(" · ");
}

function countAgents(agents: readonly ClientAgent[]): AgentsSummary {
  const out: AgentsSummary = { total: 0, serving: 0, testing: 0, ready_no_channel: 0, draft: 0, paused: 0 };
  for (const a of liveAgents(agents)) {
    out.total += 1;
    const code = a.visible_state.code;
    if (code !== "archived") out[code] += 1;
  }
  return out;
}

export type BagBar = { pct: number; tone: "ok" | "warn" | "danger" };

/**
 * La minibarra de la columna «Saldo» (prototipo §2.3): el relleno es **lo
 * gastado** de lo asignado; ámbar desde el 80 %, roja y llena sin saldo
 * asignado o agotado. Sin límite (lo cubre Auphere) no hay barra.
 */
export function bagBar(bag: Bag | null): BagBar | null {
  if (bag?.state === "unlimited") return null;
  if (!bag || bag.state === "unassigned" || !bag.assigned) return { pct: 100, tone: "danger" };
  const pct = clampPct(bag.pct_spent ?? 0);
  if (bag.state === "empty") return { pct: 100, tone: "danger" };
  return { pct, tone: pct >= 80 ? "warn" : "ok" };
}

/** Lo que la consola sabía decir de la bolsa (días y % libre), en el `title` de la barra. */
export function bagBarTitle(t: T, bag: Bag | null): string | undefined {
  if (!bag || bag.state === "unassigned" || bag.state === "unlimited") return undefined;
  const days = roundDays(bag.days_left);
  const first = days != null ? t("clients.v2.bag.days", { days }) : t("clients.v2.bag.noEstimate");
  return bag.pct_left != null ? `${first} · ${t("clients.v2.bag.pct", { pct: Math.round(bag.pct_left) })}` : first;
}

function clampPct(n: number): number {
  return Math.min(100, Math.max(0, n));
}

export type SpendSegment = { agent_id: string; name: string; spent: Money; pct: number };

/**
 * Los tramos de la barra apilada del Panel (prototipo §4.2): uno por agente con
 * gasto, de más a menos, y su ancho **sobre lo asignado**, de modo que lo que
 * queda vacío es lo disponible. La API da el gasto por agente del mes y el
 * consumido de la bolsa desde que se asignó; para que la barra cuadre con
 * «Consumido … · {pct} %», lo consumido se reparte según el gasto del mes.
 */
export function spendSegments(bag: Bag, byAgent: ClientPanel["spend_by_agent"]): SpendSegment[] {
  if (bag.state === "unassigned" || bag.state === "unlimited" || !bag.assigned?.amount_micros) return [];
  const spending = byAgent.filter((s) => s.spent.amount_micros > 0).sort((a, b) => b.spent.amount_micros - a.spent.amount_micros);
  const total = spending.reduce((sum, s) => sum + s.spent.amount_micros, 0);
  const consumed = clampPct(bag.pct_spent ?? 0);
  if (!total || !consumed) return [];
  return spending.map((s) => ({
    agent_id: s.agent_id,
    name: s.name,
    spent: s.spent,
    pct: Math.round(((consumed * s.spent.amount_micros) / total) * 100) / 100,
  }));
}

/** «1–25 oct»: del día 1 del periodo a hoy (en UTC, como lo cuenta la API), sin pasar del fin de mes. */
export function periodLabel(start: string, end: string, now: Date, locale: string): string {
  const from = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const to = today > last ? last : today < from ? from : today;
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }).formatRange(from, to);
}

/** Cuánto lleva gastado de su tope, en %. */
export function capPct(spent: Money, cap: Money): number {
  return cap.amount_micros > 0 ? Math.round((spent.amount_micros / cap.amount_micros) * 100) : 0;
}

/** Los días, redondeados como los dice el Panel («unos 4 días»). */
export function roundDays(days: number | null): number | null {
  return days == null ? null : Math.max(0, Math.round(days));
}

export function filterHref(filter: ClientFilter, q: string): string {
  const params = new URLSearchParams();
  if (filter !== "all") params.set("filter", filter);
  if (q.trim()) params.set("q", q.trim());
  const s = params.toString();
  return s ? `/clients?${s}` : "/clients";
}

export const FILTERS: readonly ClientFilter[] = ["all", "attention", "active", "archived"];

export function parseFilter(raw: string | undefined): ClientFilter {
  return (FILTERS as readonly string[]).includes(raw ?? "") ? (raw as ClientFilter) : "all";
}

/** Dónde lleva cada acción del menú que es un enlace. */
export function actionHref(action: ClientAction, ref: string): string | null {
  const r = encodeURIComponent(ref);
  switch (action) {
    case "assign_balance":
      return `/usage?client=${r}&assign=1`;
    case "request_balance":
      return `/usage?client=${r}&request=1`;
    case "new_agent":
      return `/clients/${r}/agents?new=1`;
    default:
      return null;
  }
}

/**
 * El orden del menú ⋯ (requisito 7.6, prototipo §2.3): lo que la API permite,
 * en este orden. «Nuevo agente» ya no está: el botón de la cabecera del cliente
 * lo ofrece.
 */
export const MENU_ORDER: readonly ClientAction[] = ["edit", "assign_balance", "request_balance", "archive", "restore", "delete"];

/** Lo que va tras el separador del menú: archivar o restaurar, y eliminar. */
export const MENU_LIFECYCLE: ReadonlySet<ClientAction> = new Set(["archive", "restore", "delete"]);

export function menuActions(allowed: readonly ClientAction[]): ClientAction[] {
  return MENU_ORDER.filter((a) => allowed.includes(a));
}

/** La sección de Negocio donde se arregla lo que falta. */
export function missingHref(ref: string, section: MissingSection): string {
  return `/clients/${encodeURIComponent(ref)}/business#${section}`;
}

/** Los códigos de error de la API que la consola sabe decir. */
const KNOWN_ERRORS = new Set([
  "archive_first",
  "name_mismatch",
  "legal_retention",
  "already_archived",
  "not_archived",
  "revision_conflict",
  "invalid_timezone",
  "bag_currency_locked",
]);

export function errorText(t: T, code: string | null | undefined): string {
  return code && KNOWN_ERRORS.has(code) ? t(`clients.v2.error.${code}` as MessageKey) : t("clients.v2.error.generic");
}
